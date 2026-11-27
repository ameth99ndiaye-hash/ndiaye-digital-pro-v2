(() => {
  "use strict";
  const DB_NAME = "ndiaye-digital-pro-offline";
  const STORE = "vault";
  let vault = null;
  let key = null;
  let csrfToken = null;
  const $ = (id) => document.getElementById(id);

  function openDb() {
    return new Promise((resolve, reject) => {
      const req = indexedDB.open(DB_NAME, 1);
      req.onupgradeneeded = () => req.result.createObjectStore(STORE);
      req.onsuccess = () => resolve(req.result);
      req.onerror = () => reject(req.error);
    });
  }
  async function readVault() {
    const db = await openDb();
    return new Promise((resolve, reject) => {
      const req = db.transaction(STORE, "readonly").objectStore(STORE).get("active");
      req.onsuccess = () => resolve(req.result || null);
      req.onerror = () => reject(req.error);
    });
  }
  async function writeVault(record) {
    const db = await openDb();
    return new Promise((resolve, reject) => {
      const tx = db.transaction(STORE, "readwrite");
      tx.objectStore(STORE).put(record, "active");
      tx.oncomplete = () => resolve();
      tx.onerror = () => reject(tx.error);
    });
  }
  async function deriveKey(pin, salt) {
    const material = await crypto.subtle.importKey("raw", new TextEncoder().encode(pin), "PBKDF2", false, ["deriveKey"]);
    return crypto.subtle.deriveKey({name:"PBKDF2",salt,iterations:310000,hash:"SHA-256"},material,{name:"AES-GCM",length:256},false,["encrypt","decrypt"]);
  }
  async function encryptData(data, pin) {
    const salt = crypto.getRandomValues(new Uint8Array(16));
    const iv = crypto.getRandomValues(new Uint8Array(12));
    const derived = await deriveKey(pin, salt);
    const cipher = await crypto.subtle.encrypt({name:"AES-GCM",iv},derived,new TextEncoder().encode(JSON.stringify(data)));
    return {version:1,salt:Array.from(salt),iv:Array.from(iv),cipher:Array.from(new Uint8Array(cipher)),merchant_id:data.merchant_id,updated_at:new Date().toISOString()};
  }
  async function decryptData(record, pin) {
    const salt = new Uint8Array(record.salt), iv = new Uint8Array(record.iv), cipher = new Uint8Array(record.cipher);
    const derived = await deriveKey(pin, salt);
    const plain = await crypto.subtle.decrypt({name:"AES-GCM",iv},derived,cipher);
    return JSON.parse(new TextDecoder().decode(plain));
  }
  async function save() {
    const encrypted = await encryptData(vault, $("pin").value);
    await writeVault(encrypted);
  }
  function setMessage(message) { $("queueStatus").textContent = message; }
  function pendingCount() { return vault.queue.length; }
  function applyPending(base, queue) {
    const copy = structuredClone(base);
    for (const op of queue) {
      const p = op.payload;
      if (op.type === "product_create" && !copy.products.some(x => x.id === p.product_id)) {
        copy.products.unshift({id:p.product_id,name:p.name,sku:p.sku,quantity:p.quantity,min_quantity:p.min_quantity,unit_price:p.unit_price});
      }
      if (op.type === "stock_adjust") {
        const product=copy.products.find(x=>x.id===p.product_id);
        if(product) product.quantity += p.movement_type === "IN" ? p.quantity : -p.quantity;
        copy.movements.unshift({id:op.operation_id,product_id:p.product_id,movement_type:p.movement_type,quantity:p.quantity,note:p.note||"",created_at:new Date().toISOString(),pending:true});
      }
      if (op.type === "sale_create") {
        const product=copy.products.find(x=>x.id===p.product_id);
        if(product) product.quantity -= p.quantity;
        copy.sales.unshift({id:op.operation_id,total:(product?.unit_price||0)*p.quantity,currency:"XOF",status:"pending_sync",created_at:new Date().toISOString()});
      }
    }
    return copy;
  }
  let view = null;
  function render() {
    view = applyPending(vault, vault.queue);
    $("shopName").textContent = vault.shop_name || "Ma boutique";
    $("connection").textContent = navigator.onLine ? "Connexion disponible" : "Hors connexion";
    $("queueStatus").textContent = pendingCount() ? pendingCount()+" opération(s) en attente de synchronisation." : "Toutes les opérations sont synchronisées.";
    const selectHtml = view.products.map(p=>({id:p.id,name:p.name,quantity:p.quantity})); 
    for (const formId of ["stockForm","saleForm"]) {
      const select=$(formId).elements.product_id;
      const current=select.value;
      select.replaceChildren(...selectHtml.map(p=>{const o=document.createElement("option");o.value=p.id;o.textContent=p.name+" — stock "+p.quantity;return o;}));
      if(current) select.value=current;
    }
    const table = (headers, rows) => {
      const t=document.createElement("table"), head=document.createElement("tr");
      headers.forEach(h=>{const th=document.createElement("th");th.textContent=h;head.append(th);});
      const thead=document.createElement("thead");thead.append(head);t.append(thead);
      const body=document.createElement("tbody");
      rows.forEach(row=>{const tr=document.createElement("tr");row.forEach(cell=>{const td=document.createElement("td");td.textContent=String(cell??"");tr.append(td);});body.append(tr);});
      t.append(body);return t;
    };
    const products=$("productsTable");products.replaceChildren(table(["Produit","Stock","Seuil","Prix FCFA"],view.products.map(p=>[p.name,p.quantity,p.min_quantity,p.unit_price])));
    const movements=$("movementsTable");movements.replaceChildren(table(["Date","Produit","Type","Qté"],view.movements.slice(0,15).map(m=>[m.created_at,m.products?.name||view.products.find(p=>p.id===m.product_id)?.name||"Produit",m.movement_type,m.quantity])));
    const sales=$("salesTable");sales.replaceChildren(table(["Date","Montant","Statut"],view.sales.slice(0,15).map(s=>[s.created_at,s.total+" "+(s.currency||"XOF"),s.status])));
    $("syncButton").disabled=!navigator.onLine||!pendingCount();
  }
  function addOperation(type,payload) {
    vault.queue.push({operation_id:crypto.randomUUID(),type,payload,created_at:new Date().toISOString()});
    render();
    save().then(()=>setMessage(pendingCount()+" opération(s) en attente.")).catch(()=>setMessage("Erreur de sauvegarde locale : garde cette page ouverte."));
  }
  $("unlockButton").addEventListener("click",async()=>{
    const pin=$("pin").value;
    if(pin.length<6){$("unlockMessage").textContent="Le code doit contenir au moins 6 caractères.";return;}
    try {
      const record=await readVault();
      if(!record) throw new Error("Aucune sauvegarde hors ligne trouvée. Connecte-toi à Internet et prépare d’abord le mode hors ligne.");
      vault=await decryptData(record,pin);
      key=pin;
      $("unlock").hidden=true;$("workspace").hidden=false;
      csrfToken=null;
      render();
      if(navigator.onLine) await syncQueue();
    } catch(e) { $("unlockMessage").textContent=e.message.includes("Aucune sauvegarde")?e.message:"Code incorrect ou données locales illisibles."; }
  });
  $("lockButton").addEventListener("click",()=>{vault=null;key=null;$("workspace").hidden=true;$("unlock").hidden=false;$("pin").value="";});
  $("productForm").addEventListener("submit",async e=>{
    e.preventDefault();const f=new FormData(e.currentTarget);
    const p={product_id:crypto.randomUUID(),name:String(f.get("name")).trim(),sku:String(f.get("sku")||""),quantity:Number(f.get("quantity")),min_quantity:Number(f.get("min_quantity")),unit_price:Number(f.get("unit_price"))};
    if(!p.name||![p.quantity,p.min_quantity,p.unit_price].every(Number.isFinite)||Math.min(p.quantity,p.min_quantity,p.unit_price)<0)return;
    addOperation("product_create",p);e.currentTarget.reset();render();
  });
  $("stockForm").addEventListener("submit",e=>{
    e.preventDefault();const f=new FormData(e.currentTarget);const p={product_id:String(f.get("product_id")),movement_type:String(f.get("movement_type")),quantity:Number(f.get("quantity")),note:String(f.get("note")||"")};
    const product=view.products.find(x=>x.id===p.product_id);
    if(!product||p.quantity<1||!Number.isInteger(p.quantity)||(p.movement_type==="OUT"&&product.quantity<p.quantity)){setMessage("Produit invalide ou stock insuffisant.");return;}
    addOperation("stock_adjust",p);e.currentTarget.reset();render();
  });
  $("saleForm").addEventListener("submit",e=>{
    e.preventDefault();const f=new FormData(e.currentTarget);const p={product_id:String(f.get("product_id")),quantity:Number(f.get("quantity"))};
    const product=view.products.find(x=>x.id===p.product_id);
    if(!product||p.quantity<1||!Number.isInteger(p.quantity)||product.quantity<p.quantity){setMessage("Produit invalide ou stock insuffisant.");return;}
    addOperation("sale_create",p);e.currentTarget.reset();render();
  });
  async function syncQueue() {
    if(!vault||!navigator.onLine)return;
    try {
      const bootstrap=await fetch("/api/offline-bootstrap",{credentials:"same-origin",cache:"no-store"});
      if(!bootstrap.ok) throw new Error("Reconnecte-toi à l’application pour synchroniser.");
      const data=await bootstrap.json();csrfToken=data.csrf_token;
      if(data.merchant_id!==vault.merchant_id) throw new Error("Ce compte ne correspond pas aux données hors ligne de cet appareil.");
      while(vault.queue.length) {
        const batch=vault.queue.slice(0,20);
        const response=await fetch("/api/offline-sync",{method:"POST",credentials:"same-origin",headers:{"Content-Type":"application/json","X-CSRFToken":csrfToken},body:JSON.stringify({operations:batch})});
        if(!response.ok) throw new Error("Synchronisation interrompue. Les opérations restent enregistrées.");
        const result=await response.json();
        const successful=new Set(result.results.filter(x=>x.ok).map(x=>x.operation_id));
        if(!successful.size) throw new Error("Une opération a été refusée. Elle reste en attente pour vérification.");
        vault.queue=vault.queue.filter(x=>!successful.has(x.operation_id));
        await save();
        if(successful.size<batch.length) throw new Error("Certaines opérations nécessitent une vérification. Les autres restent en attente.");
      }
      const fresh=await fetch("/api/offline-bootstrap",{credentials:"same-origin",cache:"no-store"});
      if(fresh.ok){const data=await fresh.json();vault.products=data.products;vault.movements=data.movements;vault.sales=data.sales;csrfToken=data.csrf_token;}
      await save();setMessage("Synchronisation terminée.");render();
    } catch(e) {setMessage(e.message);render();}
  }
  $("syncButton").addEventListener("click",syncQueue);
  window.addEventListener("online",()=>{if(vault)syncQueue();render();});
  window.addEventListener("offline",render);
})();
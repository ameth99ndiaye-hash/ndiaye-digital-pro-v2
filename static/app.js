(() => {
  const status=document.querySelector("[data-connection-status]");
  const installButton=document.querySelector("[data-install-app]");
  const prepareButton=document.querySelector("[data-prepare-offline]");
  const isIOS=/iphone|ipad|ipod/i.test(navigator.userAgent);
  const isStandalone=window.matchMedia("(display-mode: standalone)").matches||navigator.standalone===true;
  let installPrompt=null;
  function updateStatus(){if(!status)return;status.textContent=navigator.onLine?"En ligne":"Hors ligne";status.dataset.state=navigator.onLine?"online":"offline";}
  window.addEventListener("online",updateStatus);window.addEventListener("offline",updateStatus);updateStatus();
  if("serviceWorker" in navigator)window.addEventListener("load",()=>navigator.serviceWorker.register("/sw.js").catch(e=>console.error("Service worker registration failed",e)));
  if(installButton&&isIOS&&!isStandalone){installButton.hidden=false;installButton.textContent="Installer sur iPhone";installButton.addEventListener("click",()=>alert("Sur iPhone : touchez Partager dans Safari, puis « Sur l’écran d’accueil » et « Ajouter »."));}
  window.addEventListener("beforeinstallprompt",event=>{event.preventDefault();installPrompt=event;if(installButton&&!isIOS)installButton.hidden=false;});
  if(installButton&&!isIOS)installButton.addEventListener("click",async()=>{if(!installPrompt)return;installPrompt.prompt();await installPrompt.userChoice;installPrompt=null;installButton.hidden=true;});
  window.addEventListener("appinstalled",()=>{if(installButton)installButton.hidden=true;});

  const DB_NAME="ndiaye-digital-pro-offline",STORE="vault";
  function openDb(){return new Promise((resolve,reject)=>{const r=indexedDB.open(DB_NAME,1);r.onupgradeneeded=()=>r.result.createObjectStore(STORE);r.onsuccess=()=>resolve(r.result);r.onerror=()=>reject(r.error);});}
  async function readVault(){const db=await openDb();return new Promise((resolve,reject)=>{const r=db.transaction(STORE,"readonly").objectStore(STORE).get("active");r.onsuccess=()=>resolve(r.result||null);r.onerror=()=>reject(r.error);});}
  async function writeVault(record){const db=await openDb();return new Promise((resolve,reject)=>{const tx=db.transaction(STORE,"readwrite");tx.objectStore(STORE).put(record,"active");tx.oncomplete=resolve;tx.onerror=()=>reject(tx.error);});}
  async function makeKey(pin,salt){const material=await crypto.subtle.importKey("raw",new TextEncoder().encode(pin),"PBKDF2",false,["deriveKey"]);return crypto.subtle.deriveKey({name:"PBKDF2",salt,iterations:310000,hash:"SHA-256"},material,{name:"AES-GCM",length:256},false,["encrypt"]);}
  async function encrypt(data,pin){const salt=crypto.getRandomValues(new Uint8Array(16)),iv=crypto.getRandomValues(new Uint8Array(12)),key=await makeKey(pin,salt);const cipher=await crypto.subtle.encrypt({name:"AES-GCM",iv},key,new TextEncoder().encode(JSON.stringify(data)));return {version:1,salt:Array.from(salt),iv:Array.from(iv),cipher:Array.from(new Uint8Array(cipher)),merchant_id:data.merchant_id,updated_at:new Date().toISOString()};}
  if(prepareButton)prepareButton.addEventListener("click",async()=>{
    if(!navigator.onLine){alert("Connecte-toi à Internet pour préparer les données hors ligne.");return;}
    const pin=prompt("Crée un code secret hors ligne d’au moins 6 caractères. Ne le partage avec personne.");
    if(!pin||pin.length<6){alert("Le code doit contenir au moins 6 caractères.");return;}
    const confirm=prompt("Confirme ton code secret hors ligne.");
    if(pin!==confirm){alert("Les deux codes ne correspondent pas.");return;}
    prepareButton.disabled=true;prepareButton.textContent="Préparation…";
    try{
      const response=await fetch("/api/offline-bootstrap",{credentials:"same-origin",cache:"no-store"});
      if(!response.ok)throw new Error("Impossible de charger les données. Reconnecte-toi.");
      const data=await response.json();
      const old=await readVault();
      if(old&&old.merchant_id!==data.merchant_id&&!window.confirm("Un autre commerce est déjà enregistré sur cet appareil. Remplacer ses données hors ligne ? Synchronise d’abord ses opérations en attente."))return;
      const vault={merchant_id:data.merchant_id,shop_name:data.shop_name,products:data.products||[],movements:data.movements||[],sales:data.sales||[],queue:[]};
      await writeVault(await encrypt(vault,pin));
      alert("Mode hors ligne préparé pour "+data.shop_name+". Garde ton code secret : il sera nécessaire pour ouvrir tes données sans Internet.");
    }catch(e){alert(e.message||"Préparation impossible.");}
    finally{prepareButton.disabled=false;prepareButton.textContent="Préparer le mode hors ligne";}
  });
})();
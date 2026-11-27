const CACHE_NAME = "ndiaye-digital-pro-shell-v2";
const SHELL = [
  "/static/style.css",
  "/static/app.js",
  "/static/manifest.webmanifest",
  "/static/app-icon.svg",
  "/static/offline.html",
  "/static/offline-workspace.html",
  "/static/offline-workspace.js",
  "/offline-workspace"
];
self.addEventListener("install", event => {
  event.waitUntil(caches.open(CACHE_NAME).then(cache => cache.addAll(SHELL)));
  self.skipWaiting();
});
self.addEventListener("activate", event => {
  event.waitUntil(caches.keys().then(keys => Promise.all(
    keys.filter(key => key.startsWith("ndiaye-digital-pro-") && key !== CACHE_NAME).map(key => caches.delete(key))
  )));
  self.clients.claim();
});
self.addEventListener("fetch", event => {
  const req=event.request, url=new URL(req.url);
  if(req.method!=="GET" || url.origin!==self.location.origin)return;
  if(url.pathname.startsWith("/api/") || ["/login","/logout","/dashboard","/products","/stock","/sales","/subscription","/admin"].includes(url.pathname))return;
  if(url.pathname.startsWith("/static/") || url.pathname==="/offline-workspace"){
    event.respondWith(caches.match(req).then(cached=>cached||fetch(req).then(res=>{
      if(res.ok){const copy=res.clone();caches.open(CACHE_NAME).then(cache=>cache.put(req,copy));}
      return res;
    })));
    return;
  }
  if(req.mode==="navigate") event.respondWith(fetch(req).catch(async()=>{
    const cache=await caches.open(CACHE_NAME);
    return (await cache.match("/static/offline.html")) || new Response("Connexion indisponible.",{status:503});
  }));
});
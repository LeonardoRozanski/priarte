/* PriArte Ateliê — service worker: app funciona offline e instalável (PWA) */
const CACHE = 'priarte-v1';
const ARQS = ['./', './index.html'];

self.addEventListener('install', ev => {
  ev.waitUntil(caches.open(CACHE).then(c => c.addAll(ARQS)).then(() => self.skipWaiting()));
});
self.addEventListener('activate', ev => {
  ev.waitUntil(
    caches.keys().then(keys => Promise.all(keys.filter(k => k !== CACHE).map(k => caches.delete(k)))).then(() => self.clients.claim())
  );
});
self.addEventListener('fetch', ev => {
  if (ev.request.method !== 'GET') return;
  ev.respondWith(
    caches.match(ev.request).then(hit => hit || fetch(ev.request).then(resp => {
      const copia = resp.clone();
      caches.open(CACHE).then(c => c.put(ev.request, copia)).catch(() => {});
      return resp;
    }).catch(() => caches.match('./index.html')))
  );
});

/* PriArte: busca a versão atual do app; usa a cópia salva quando está offline. */
const CACHE = 'priarte-v2';
const ARQS = ['./', './index.html'];
const APP_URLS = new Set(ARQS.map(path => new URL(path, self.registration.scope).href));

self.addEventListener('install', ev => {
  ev.waitUntil(caches.open(CACHE).then(c => c.addAll(ARQS)).then(() => self.skipWaiting()));
});
self.addEventListener('activate', ev => {
  ev.waitUntil(
    caches.keys().then(keys => Promise.all(keys.filter(k => k.startsWith('priarte-') && k !== CACHE).map(k => caches.delete(k)))).then(() => self.clients.claim())
  );
});
self.addEventListener('fetch', ev => {
  // Dados e tokens da nuvem nunca entram no cache do app.
  if (ev.request.method !== 'GET' || !APP_URLS.has(ev.request.url)) return;
  ev.respondWith(fetch(ev.request, { cache: 'no-store' }).then(resp => {
    if (resp.ok) {
      const copia = resp.clone();
      ev.waitUntil(caches.open(CACHE).then(c => c.put(ev.request, copia)).catch(() => {}));
      return resp;
    }
    throw new Error('App indisponível');
  }).catch(async () => {
    const cache = await caches.open(CACHE);
    return await cache.match(ev.request) || await cache.match('./index.html') || Response.error();
  }));
});

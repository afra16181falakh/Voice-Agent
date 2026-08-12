// Minimal service worker -- required for PWA installability. Network-first,
// no offline app shell caching yet (voice calls need a live connection
// anyway, so offline support isn't meaningful here).
self.addEventListener('install', (e) => { self.skipWaiting(); });
self.addEventListener('activate', (e) => { self.clients.claim(); });
self.addEventListener('fetch', (e) => {
  e.respondWith(fetch(e.request).catch(() => new Response('Offline', { status: 503 })));
});

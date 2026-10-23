const CACHE = 'cs-helper-shell-v2';
const SHELL = [
  '/',
  '/static/mobile.css',
  '/static/mobile.js',
  '/static/replay-core.js',
  '/static/icon.svg',
  '/manifest.webmanifest',
];

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches
      .open(CACHE)
      .then((cache) => cache.addAll(SHELL))
      .then(() => self.skipWaiting())
      .catch(() => self.skipWaiting()),
  );
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches
      .keys()
      .then((keys) => Promise.all(keys.filter((key) => key !== CACHE).map((key) => caches.delete(key))))
      .then(() => self.clients.claim()),
  );
});

self.addEventListener('fetch', (event) => {
  const url = new URL(event.request.url);
  if (url.origin !== location.origin) return;
  // Live data must never be served from cache.
  if (url.pathname.startsWith('/api/') || url.pathname.startsWith('/ws')) return;
  if (event.request.method !== 'GET') return;

  // Network first: the shell is served from a LAN box that changes on every
  // release, and a cache-first shell means the phone keeps running last week's
  // JS until the second reload. Cache is only the offline fallback.
  event.respondWith(
    fetch(event.request)
      .then((response) => {
        if (response.ok) {
          const copy = response.clone();
          caches.open(CACHE).then((cache) => cache.put(event.request, copy));
        }
        return response;
      })
      .catch(() => caches.match(event.request).then((cached) => cached || Response.error())),
  );
});

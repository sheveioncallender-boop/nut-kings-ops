'use strict';
const CACHE = 'nut-kings-ops-v1.0.0';
const SHELL = [
  '/nutkings/',
  '/nut_kings_ops/static/workspace/app-v1.0.0.css',
  '/nut_kings_ops/static/workspace/app-v1.0.0.js',
  '/nut_kings_ops/static/img/nut_kings_logo.png',
  '/nut_kings_ops/static/description/icon-192.png',
  '/nut_kings_ops/static/description/icon-512.png',
  '/nutkings/manifest.webmanifest'
];
self.addEventListener('install', (event) => {
  event.waitUntil(caches.open(CACHE).then((cache) => cache.addAll(SHELL)).then(() => self.skipWaiting()));
});
self.addEventListener('activate', (event) => {
  event.waitUntil(caches.keys().then((keys) => Promise.all(keys.filter((key) => key.startsWith('nut-kings-ops-') && key !== CACHE).map((key) => caches.delete(key)))).then(() => self.clients.claim()));
});
self.addEventListener('fetch', (event) => {
  const request = event.request;
  if (request.method !== 'GET') return;
  const url = new URL(request.url);
  if (url.origin !== self.location.origin) return;
  if (url.pathname.startsWith('/nutkings/api/') || url.pathname.startsWith('/web/')) return;
  if (url.pathname === '/nutkings/' || url.pathname.startsWith('/nut_kings_ops/static/')) {
    event.respondWith(caches.match(request).then((cached) => cached || fetch(request).then((response) => {
      if (response.ok) caches.open(CACHE).then((cache) => cache.put(request, response.clone()));
      return response;
    }).catch(() => caches.match('/nutkings/'))));
  }
});

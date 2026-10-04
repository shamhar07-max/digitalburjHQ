'use strict';
/* DigitalBurj HQ service worker: caches the app shell only. API responses and downloads are never
   stored, so private data cannot outlive a sign-out on a shared device. */
const VERSION = 'hq-shell-v2';
const SHELL = ['./', 'style.css', 'homepage-components.css', 'hq-motion.css', 'hq-calm.css', 'hq-icons.js', 'hq-modules.js',
  'pwa.js', 'hq-collab.js', 'hq-files.js', 'hq-topics.js', 'hq-integrations.js', 'app.js', 'offline.html', 'offline.css', 'icons/icon-192.png', 'brand/favicon.png'];

self.addEventListener('install', e => {
  e.waitUntil(caches.open(VERSION).then(c => c.addAll(SHELL)).then(() => self.skipWaiting()));
});
self.addEventListener('activate', e => {
  e.waitUntil(caches.keys().then(keys => Promise.all(keys.filter(k => k !== VERSION).map(k => caches.delete(k))))
    .then(() => self.clients.claim()));
});
self.addEventListener('fetch', e => {
  const req = e.request, url = new URL(req.url);
  if (req.method !== 'GET' || url.origin !== location.origin || url.pathname.startsWith('/api/')) return;
  if (req.mode === 'navigate') {
    e.respondWith(fetch(req).catch(() => caches.match('offline.html')));
    return;
  }
  e.respondWith(fetch(req).then(res => {
    if (res.ok && SHELL.some(p => url.pathname.endsWith(p.replace('./', '') || 'index.html'))) {
      const copy = res.clone();
      caches.open(VERSION).then(c => c.put(req, copy));
    }
    return res;
  }).catch(() => caches.match(req)));
});

/* SchoolOS PWA Service Worker — بوابة ولي الأمر */
const CACHE_NAME = 'schoolos-parents-v1';
const OFFLINE_URL = '/parents/offline/';

const CACHE_ASSETS = [
  '/parents/',
  '/parents/offline/',
  '/static/css/custom.css',
  'https://cdn.tailwindcss.com',
];

/* ── Install: cache core assets ── */
self.addEventListener('install', event => {
  event.waitUntil(
    caches.open(CACHE_NAME).then(cache => {
      return cache.addAll(CACHE_ASSETS).catch(() => {});
    }).then(() => self.skipWaiting())
  );
});

/* ── Activate: clean old caches ── */
self.addEventListener('activate', event => {
  event.waitUntil(
    caches.keys().then(keys =>
      Promise.all(keys.filter(k => k !== CACHE_NAME).map(k => caches.delete(k)))
    ).then(() => self.clients.claim())
  );
});

/* ── Fetch: network-first, fallback to cache ── */
self.addEventListener('fetch', event => {
  if (event.request.method !== 'GET') return;

  const url = new URL(event.request.url);

  // API calls — always network, return error JSON if offline
  if (url.pathname.startsWith('/api/')) {
    event.respondWith(
      fetch(event.request).catch(() =>
        new Response(JSON.stringify({ error: 'أنت غير متصل بالإنترنت' }), {
          headers: { 'Content-Type': 'application/json' },
          status: 503,
        })
      )
    );
    return;
  }

  // Parents pages — network-first with cache fallback
  if (url.pathname.startsWith('/parents/')) {
    event.respondWith(
      fetch(event.request)
        .then(response => {
          const clone = response.clone();
          caches.open(CACHE_NAME).then(cache => cache.put(event.request, clone));
          return response;
        })
        .catch(async () => {
          const cached = await caches.match(event.request);
          if (cached) return cached;
          return caches.match(OFFLINE_URL);
        })
    );
    return;
  }

  // Static assets — cache-first
  event.respondWith(
    caches.match(event.request).then(cached => cached || fetch(event.request))
  );
});

/* ── Push Notifications ── */
self.addEventListener('push', event => {
  const data = event.data ? event.data.json() : {};
  const title = data.title || 'SchoolOS';
  const options = {
    body:    data.body || 'لديك إشعار جديد من المدرسة',
    icon:    '/static/icons/icon-192.png',
    badge:   '/static/icons/badge-72.png',
    dir:     'rtl',
    lang:    'ar',
    vibrate: [200, 100, 200],
    data:    { url: data.url || '/parents/' },
    actions: [
      { action: 'open',    title: 'فتح',  icon: '/static/icons/check.png' },
      { action: 'dismiss', title: 'إغلاق', icon: '/static/icons/close.png' },
    ],
  };
  event.waitUntil(self.registration.showNotification(title, options));
});

self.addEventListener('notificationclick', event => {
  event.notification.close();
  if (event.action === 'dismiss') return;
  const url = event.notification.data?.url || '/parents/';
  event.waitUntil(
    clients.matchAll({ type: 'window' }).then(list => {
      const existing = list.find(c => c.url.includes('/parents/'));
      if (existing) return existing.focus();
      return clients.openWindow(url);
    })
  );
});

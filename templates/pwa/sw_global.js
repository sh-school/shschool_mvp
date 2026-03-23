/* SchoolOS — Global Service Worker v5.2
   يُغطّي جميع المسارات ما عدا /parents/ (التي لها SW خاص)
*/
var CACHE_NAME = 'schoolos-global-v1';
var STATIC_ASSETS = [
  '/static/css/custom.css',
  '/static/css/tailwind.min.css',
  '/static/js/app.js',
  '/offline/'
];

self.addEventListener('install', function (e) {
  e.waitUntil(
    caches.open(CACHE_NAME).then(function (cache) {
      return cache.addAll(STATIC_ASSETS);
    })
  );
  self.skipWaiting();
});

self.addEventListener('activate', function (e) {
  e.waitUntil(
    caches.keys().then(function (keys) {
      return Promise.all(
        keys
          .filter(function (k) { return k !== CACHE_NAME; })
          .map(function (k) { return caches.delete(k); })
      );
    })
  );
  self.clients.claim();
});

self.addEventListener('fetch', function (e) {
  var url = e.request.url;

  /* لا تتدخل في /parents/ — لها SW خاص بها */
  if (url.includes('/parents/')) return;

  /* طلبات POST / غير-GET — تجاوز */
  if (e.request.method !== 'GET') return;

  /* الملفات الثابتة → cache-first */
  if (url.includes('/static/')) {
    e.respondWith(
      caches.match(e.request).then(function (cached) {
        return cached || fetch(e.request).then(function (res) {
          var clone = res.clone();
          caches.open(CACHE_NAME).then(function (c) { c.put(e.request, clone); });
          return res;
        });
      })
    );
    return;
  }

  /* الصفحات → network-first مع fallback للـ offline */
  e.respondWith(
    fetch(e.request).catch(function () {
      return caches.match(e.request).then(function (cached) {
        return cached || caches.match('/offline/');
      });
    })
  );
});

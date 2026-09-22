/* SchoolOS PWA Service Worker — بوابة ولي الأمر

   والأصلُ غيرُ المبصوم لا يُخدَم من الذاكرة أوّلاً: عنوانُه ثابتٌ ومحتواه
   يتغيّر، فيبقى القديمُ إلى الأبد ولا يُقرأ `Cache-Control` أصلاً — عاملُ
   الخدمة أمام الشبكة والترويسات. انظر `templates/pwa/sw_global.js`.

   ولا تُخزَّن صفحةٌ شخصيّة (P1-3). كانت كلُّ صفحةٍ تحت /parents/ تُحفظ بعد
   كلّ فتح — درجاتُ الابن وغيابُه وسلوكُه — وتبقى على الجهاز بعد الخروج،
   وتُعرض لمن يفتحه بلا شبكة، ولو كان جهازاً مشتركاً في البيت. وكانت تُحفظ
   بلا نظرٍ في حالة الردّ ولا في `no-store` الذي يضعه الخادمُ لكلّ صفحةِ
   مسجَّل. فالصفحاتُ الآن من الشبكة وحدَها، وعند الانقطاع صفحةُ «غير متصل»؛
   ولا يُحفظ إلّا الثابتُ تحت /static/. ورفعُ الإصدار يمحو v2 وما فيها. */
const CACHE_NAME = 'schoolos-parents-v3';
const OFFLINE_URL = '/parents/offline/';

/* لا يُخزَّن مسبقاً إلّا صفحةُ الانقطاع — لا بياناتِ فيها. */
const CACHE_ASSETS = [OFFLINE_URL];

const isStatic = (url) => url.origin === self.location.origin && url.pathname.startsWith('/static/');
const cacheable = (res) =>
  res && res.ok && !/no-store|private/i.test(res.headers.get('Cache-Control') || '');

/* بصمةُ المحتوى: `name.<hex8+>.ext` — ما يكتبه manifest storage. */
const FINGERPRINTED = /\.[0-9a-f]{8,}\.[a-z0-9]+$/i;
const isFingerprinted = (url) => FINGERPRINTED.test(url.split('?')[0].split('#')[0]);

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

  // التنقّلُ بين الصفحات: من الشبكة وحدَها، وعند الانقطاع صفحةُ «غير متصل».
  if (event.request.mode === 'navigate') {
    event.respondWith(
      fetch(event.request).catch(() => caches.match(OFFLINE_URL))
    );
    return;
  }

  // ما ليس ثابتاً (أجزاءُ HTMX، ملفّاتُ /dbmedia/، …) لا يمسّه العامل.
  if (!isStatic(url)) return;

  // الأصولُ الثابتة: المبصومُ من الذاكرة أوّلاً، وغيرُه من الشبكة أوّلاً
  // مع سقوطٍ إلى الذاكرة عند الانقطاع — فتبقى فائدةُ العمل دون شبكة.
  if (isFingerprinted(event.request.url)) {
    event.respondWith(
      caches.match(event.request).then(cached => cached || fetch(event.request).then(res => {
        if (cacheable(res)) {
          const clone = res.clone();
          caches.open(CACHE_NAME).then(cache => cache.put(event.request, clone));
        }
        return res;
      }))
    );
    return;
  }
  event.respondWith(
    fetch(event.request)
      .then(res => {
        if (cacheable(res)) {
          const clone = res.clone();
          caches.open(CACHE_NAME).then(cache => cache.put(event.request, clone));
        }
        return res;
      })
      .catch(() => caches.match(event.request))
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
    // بلا أيقوناتٍ للأزرار: check.png وclose.png لم يوجدا قطّ.
    actions: [
      { action: 'open',    title: 'فتح' },
      { action: 'dismiss', title: 'إغلاق' },
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

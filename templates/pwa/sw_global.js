/* SchoolOS — Global Service Worker v5.3
   يُغطّي جميع المسارات ما عدا /parents/ (التي لها SW خاص)

   ── لِمَ لا تُخزَّن كلُّ `/static/` تخزيناً أوّليّاً ──────────────────────
   كان الشرطُ `url.includes('/static/')` يخدم كلَّ أصلٍ من الذاكرة أوّلاً بلا
   مراجعة، والذاكرةُ باسمٍ ثابت. فأوّلُ نسخةٍ تُحمَّل من `custom.css` تبقى
   على جهاز المستخدم إلى الأبد: `Cache-Control: max-age=0` لا يُقرأ أصلاً،
   لأنّ عاملَ الخدمة يجلس أمام الشبكة والترويسات جميعاً. و`Ctrl+Shift+R`
   وحدَه يتخطّاه — وهو ما كان المستخدم يفعله في كلّ مرّة.

   والتخزينُ الأوّليُّ صحيحٌ حيث يحمل الاسمُ بصمةَ محتواه: في الإنتاج
   `custom.06dcd9eb.css` عبر `CompressedManifestStaticFilesStorage`، فتغيُّرُ
   المحتوى يغيّر العنوان، والمخزَّنُ بالعنوان القديم لا يُطلب. وأمّا في
   التطوير فالعنوانُ ثابتٌ والمحتوى يتغيّر كلَّ دقيقة.

   فالتفرقةُ بالبصمة لا بالمسار: المبصومُ من الذاكرة، وغيرُه من الشبكة مع
   سقوطٍ إلى الذاكرة عند الانقطاع — فتبقى فائدةُ العمل دون شبكة.
*/
var CACHE_NAME = 'schoolos-global-v2';

/* لا يُخزَّن مسبقاً إلّا ما لا يشيخ. وأصولُ التطوير غيرُ مبصومةٍ فتُترك
   للشبكة، وأصولُ الإنتاج مبصومةٌ بأسماءٍ لا تُعرف هنا. */
var STATIC_ASSETS = ['/offline/'];

/* بصمةُ المحتوى: `name.<hex8+>.ext` — ما يكتبه manifest storage. */
var FINGERPRINTED = /\.[0-9a-f]{8,}\.[a-z0-9]+$/i;

function isFingerprinted(url) {
  return FINGERPRINTED.test(url.split('?')[0].split('#')[0]);
}

function cacheFirst(request) {
  return caches.match(request).then(function (cached) {
    return cached || fetch(request).then(function (res) {
      if (res && res.ok) {
        var clone = res.clone();
        caches.open(CACHE_NAME).then(function (c) { c.put(request, clone); });
      }
      return res;
    });
  });
}

function networkFirst(request) {
  return fetch(request).then(function (res) {
    if (res && res.ok) {
      var clone = res.clone();
      caches.open(CACHE_NAME).then(function (c) { c.put(request, clone); });
    }
    return res;
  }).catch(function () {
    return caches.match(request);
  });
}

self.addEventListener('install', function (e) {
  e.waitUntil(
    caches.open(CACHE_NAME).then(function (cache) {
      return cache.addAll(STATIC_ASSETS);
    })
  );
  self.skipWaiting();
});

/* رفعُ اسم الذاكرة يجعل هذا المعالجَ يمحو النسخَ المسمومةَ من تلقائه،
   فلا يحتاج المستخدمُ إلى إلغاء تسجيل العامل بيده. */
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

  if (url.includes('/static/')) {
    e.respondWith(isFingerprinted(url) ? cacheFirst(e.request) : networkFirst(e.request));
    return;
  }

  /* الصفحات → network-first مع fallback للـ offline.
     ولا تُخزَّن: صفحةُ مستخدمٍ مسجَّلٍ تخرج بـ`no-store` (انظر
     `PrivateHtmlNoStoreMiddleware`)، وتخزينُها هنا يلتفّ على ذلك. */
  e.respondWith(
    fetch(e.request).catch(function () {
      return caches.match(e.request).then(function (cached) {
        return cached || caches.match('/offline/');
      });
    })
  );
});

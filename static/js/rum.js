/* RUM (Q-04): قياسُ LCP وINP وCLS ميدانيّاً وإرسالُ حمولةٍ مجمَّعةٍ بلا هويّةٍ عند مغادرة الصفحة.
   الخصوصيّة (PDPPL): لا مسارَ ولا مرجعَ ولا وكيلَ مستخدمٍ ولا تخزينَ ولا معرّفَ — أرقامٌ وفئةُ جهازٍ ونمطُ
   تخطيطٍ من قائمةٍ ثابتة. `tests/test_rum_client.py` يحرس ذلك.
   مطفأٌ ما لم يُصدر `base.html` هذا السكربتَ: يلزمه `RUM_ENDPOINT` غيرُ فارغ (الأصل فارغ) — مفتاحُ الإيقاف. */
(function () {
  'use strict';
  var cfg = window.APP_CONFIG && window.APP_CONFIG.rum;
  if (!cfg || !cfg.endpoint || !window.PerformanceObserver || !navigator.sendBeacon) return;
  if (document.visibilityState === 'hidden' || !(Math.random() * 100 < cfg.sample)) return;   // صفحةٌ بالخلفيّة: LCP لا معنى له

  var LAYOUTS = ['dashboard', 'hub', 'list', 'detail', 'form', 'sheet', 'report', 'custom'];   // D-16
  var NAV = ['navigate', 'reload', 'back_forward', 'prerender'];
  var NET = ['slow-2g', '2g', '3g', '4g'];

  var lcp = null, cls = 0, winStart = 0, winPrev = 0, winSum = 0, taps = [], sent = false;

  function watch(type, each, opts) {
    try {
      var o = new PerformanceObserver(function (list) { list.getEntries().forEach(each); });
      var init = { type: type, buffered: true };
      for (var k in opts) init[k] = opts[k];
      o.observe(init);
    } catch (e) { /* المتصفّحُ لا يعرف هذا النوع */ }
  }

  watch('largest-contentful-paint', function (e) { lcp = e.startTime; });

  watch('layout-shift', function (e) {   // نافذةُ الجلسة كما تعرّفها Google: فجواتٌ دون ثانية وسقفُها خمس
    if (e.hadRecentInput) return;
    if (winSum && e.startTime - winPrev < 1000 && e.startTime - winStart < 5000) {
      winSum += e.value;
    } else {
      winSum = e.value;
      winStart = e.startTime;
    }
    winPrev = e.startTime;
    if (winSum > cls) cls = winSum;
  });

  var byId = {};
  watch('event', function (e) {
    if (!e.interactionId) return;
    var old = byId[e.interactionId];
    if (old === undefined) taps.push(e.interactionId);
    if (old === undefined || e.duration > old) byId[e.interactionId] = e.duration;
  }, { durationThreshold: 16 });

  function inp() {   // أبطأُ تفاعلٍ، ومن كلّ خمسين تفاعلاً يُتجاهَل الأبطأُ (كما يفعل INP)
    if (!taps.length) return null;
    var all = taps.map(function (id) { return byId[id]; }).sort(function (a, b) { return b - a; });
    return Math.round(all[Math.min(all.length - 1, Math.floor(all.length / 50))]);
  }

  function pick(list, value) { return list.indexOf(value) === -1 ? null : value; }

  var main = document.getElementById('main-content');
  var layout = null;   // نمطُ أوّل صفحةٍ حُمّلت؛ ولا يُقرأ منها غيرُ اسم النمط
  if (main) {
    for (var i = 0; i < LAYOUTS.length; i++) {
      if (main.classList.contains('layout-' + LAYOUTS[i])) layout = LAYOUTS[i];
    }
  }

  function flush() {
    if (sent || (lcp === null && !taps.length)) return;
    sent = true;
    var coarse = matchMedia('(pointer: coarse)').matches;
    var nav = performance.getEntriesByType('navigation')[0];
    var body = JSON.stringify({
      v: 1,
      lcp: lcp === null ? null : Math.round(lcp),
      inp: inp(),
      cls: Math.round(cls * 1000) / 1000,
      dev: !coarse ? 'desktop' : (Math.min(screen.width, screen.height) < 600 ? 'phone' : 'tablet'),
      lay: layout,
      nav: nav ? pick(NAV, nav.type) : null,
      net: navigator.connection ? pick(NET, navigator.connection.effectiveType) : null
    });
    navigator.sendBeacon(cfg.endpoint, new Blob([body], { type: 'application/json' }));
  }

  document.addEventListener('visibilitychange', function () {
    if (document.visibilityState === 'hidden') flush();
  });
  addEventListener('pagehide', flush);
})();

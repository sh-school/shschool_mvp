/**
 * app-mode.js — المنصّةُ مثبَّتةً تطبيقاً: لا صفحةَ بلا طريقِ رجوع.
 *
 * التطبيقُ المثبَّت (`display-mode: standalone|fullscreen`) بلا شريطِ متصفّح،
 * وآيفون لا يعطي فيه زرَّ رجوعٍ ولا إيماءةً يُعتمد عليها. فكلُّ ما يفترض
 * متصفّحاً يصير فخّاً (2026-09-14، بلاغُ المطوّر بلقطةٍ من آيفون):
 *
 *   ١. الملفّات (PDF، Excel، مرفق): انتقلت إلى `export-center.js` (VI-30أ) — مركزُ التصدير الواحد لكلّ رابطٍ أو زرٍّ يحمل `data-app-file`:
 *      يُجلب الملفُّ في الخلفيّة بإشعار «جارٍ التحضير»، ويُسلَّم في التطبيق المثبَّت على جهاز لمسٍ لقائمة المشاركة (معاينةٌ، حفظٌ، طباعةٌ، واتساب)
 *      بدل أن يُعرض مكانَ المنصّة بعارض النظام فلا يُخرج منه شيء. وحارسُ الوسم في tests/test_app_mode_no_dead_ends.py.
 *   ٢. «لسانٌ جديد» (`target="_blank"`) لصفحةٍ من المنصّة يُفتح في النافذة نفسها.
 *      أمّا الملفُّ فلا: حيث لا مشاركة يبقى لسانُه الجديد، ولا يحلّ محلّ التطبيق.
 *   ٣. الأوراقُ المستقلّة (قوالبُ الطباعة بلا إطار المنصّة) تحمل شريطَ
 *      «رجوع إلى المنصّة» — `components/app_back_bar.html` — يظهر هنا وحدَه.
 *
 * وخارج التطبيق لا يتغيّر شيء: المتصفّحُ له أزرارُه.
 */
(function () {
  'use strict';

  var STANDALONE = '(display-mode: standalone), (display-mode: fullscreen)';

  function matches(query) {
    return !!(window.matchMedia && window.matchMedia(query).matches);
  }

  // يُسأل عند كلّ ضغطة لا مرّةً عند التحميل — فيُختبر من الطرفيّة بتبديل matchMedia.
  function inApp() {
    return matches(STANDALONE) || window.navigator.standalone === true;
  }

  function sameOrigin(url) {
    try {
      return new URL(url, window.location.href).origin === window.location.origin;
    } catch (e) {
      return false;
    }
  }

  /* ── ٢. «لسانٌ جديد» في النافذة نفسها ────────────────────────── */

  document.addEventListener('click', function (event) {
    if (event.defaultPrevented || event.button !== 0 || !inApp()) return;
    var el = event.target.closest && event.target.closest('a[href], button[type="submit"], button:not([type])');
    if (!el) return;

    // الملفّاتُ لمركز التصدير (`export-center.js`): ما لم يعالجه (بلا إشعارٍ عائم) يُترك لسلوكه ولسانُه الجديدُ إن كان له.
    if (el.hasAttribute('data-app-file')) return;

    if (el.tagName === 'A' && el.target === '_blank' && sameOrigin(el.href)) {
      event.preventDefault();
      window.location.assign(el.href);
    } else if (el.tagName === 'BUTTON' && el.getAttribute('formtarget') === '_blank') {
      el.removeAttribute('formtarget'); // يُرسَل النموذجُ في النافذة نفسها
    }
  });

  /* ── ٣. شريطُ الرجوع في الأوراق المستقلّة ─────────────────────── */

  var ORIGIN_KEY = 'app-back:' + window.location.pathname;

  // من أين دخلنا الورقة: أوّلُ مرجعٍ من صفحةٍ أخرى. وتغييرُ اختيار الورقة (المعلّم،
  // الورق) يعيد تحميلَها ومرجعُها هي نفسُها — فلا يُكتب فوق الأصل.
  function rememberOrigin() {
    var ref = document.referrer;
    if (!ref || !sameOrigin(ref)) return;
    if (new URL(ref).pathname === window.location.pathname) return;
    try { window.sessionStorage.setItem(ORIGIN_KEY, ref); } catch (e) { /* تخزينٌ محجوب */ }
  }

  function originUrl() {
    try { return window.sessionStorage.getItem(ORIGIN_KEY); } catch (e) { return null; }
  }

  // الورقةُ بلا meta viewport يصغّرها الجوالُ بقدر عرضها على عرض الشاشة — فيُكبَّر
  // الشريطُ بالقدر نفسه. وعرضُ الشاشة بحسب الاتّجاه: screen.width في iOS عرضُ
  // الوضع العموديّ دائماً.
  function scaleBars(bars) {
    var a = window.screen.width || 1;
    var b = window.screen.height || a;
    var screenWidth = matches('(orientation: landscape)') ? Math.max(a, b) : Math.min(a, b);
    var scale = document.documentElement.clientWidth / screenWidth;
    scale = Math.min(Math.max(scale, 1), 4);
    for (var i = 0; i < bars.length; i++) bars[i].style.zoom = String(scale);
  }

  function initBackBars() {
    // داخل إطار المنصّة للورقة إطارٌ حولها — فلا شريطَ هناك.
    if (!inApp() || window.top !== window) return;
    var bars = document.querySelectorAll('[data-app-back-bar]');
    if (!bars.length) return;
    rememberOrigin();
    scaleBars(bars);
    for (var i = 0; i < bars.length; i++) bars[i].hidden = false;
    var rescale = function () { scaleBars(bars); };
    window.addEventListener('resize', rescale);
    window.addEventListener('orientationchange', rescale);
  }

  document.addEventListener('click', function (event) {
    var back = event.target.closest && event.target.closest('[data-app-back]');
    if (!back) return;
    var origin = originUrl();
    if (!origin) return; // الرابطُ نفسُه: الرئيسيّة
    event.preventDefault();
    window.location.assign(origin);
  });

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initBackBars);
  } else {
    initBackBars();
  }
})();

/**
 * icon-update-notice.js — بطاقةُ «تغيّرت أيقونة التطبيق» لمن ثبّت المنصّة قبل تغيير الأيقونة (W-20261011-012).
 *
 * لِمَ بطاقة؟ استبدالُ صورةٍ لا يغيّر الأيقونةَ عند من ثبّت التطبيق: Chrome 144+ لا يعيد تنزيلَ أيقونةٍ تغيّر محتواها
 * ورابطُها واحد (فالأيقوناتُ الآن في مجلّدٍ مرقَّم `static/icons/v2/`)، ويعرض «مراجعة تحديث التطبيق» في قائمته فللمستخدم أن يتجاهله؛
 * وiOS يحفظ الأيقونةَ لحظةَ الإضافة ولا طريقَ من الخادم لتغييرها.
 *
 * من يراها؟ التطبيقُ المثبَّتُ وحدَه (`display-mode: standalone|fullscreen` أو `navigator.standalone`)، ومرّةً واحدة:
 *   - مَن ثبّت بعد التغيير لا تظهر له: على أندرويد والحاسوب يُسجَّل حدثُ `appinstalled`؛ وعلى iOS التثبيتُ الجديد
 *     يبدأ بمخزنٍ فارغٍ تماماً، فمخزنٌ فارغٌ في أوّل تشغيلٍ يعني تثبيتاً جديداً فيُعلَّم ولا تُعرض له.
 *   - مَن ثبّت قبل التغيير مخزنُه غيرُ فارغٍ ولا علامةَ فيه: تظهر له حتى يُغلقها فتُسجَّل العلامة.
 * ورقمُ النسخة `VERSION` يرتفع مع كلّ تغييرٍ آخرَ للأيقونة فتعود البطاقةُ لمن لم يرَ الجديد.
 */
(function () {
  'use strict';

  var KEY = 'schoolos.iconV';
  var VERSION = '2'; // يطابق مجلّد static/icons/v2/
  var STANDALONE = '(display-mode: standalone), (display-mode: fullscreen)';

  function read() {
    try { return window.localStorage.getItem(KEY); } catch (e) { return VERSION; /* بلا مخزنٍ لا تُعرض */ }
  }
  function mark() {
    try { window.localStorage.setItem(KEY, VERSION); } catch (e) { /* لا مخزن */ }
  }
  function storageIsEmpty() {
    try { return window.localStorage.length === 0; } catch (e) { return false; }
  }
  function inApp() {
    return !!(window.matchMedia && window.matchMedia(STANDALONE).matches) || window.navigator.standalone === true;
  }
  function isIos() {
    var ua = window.navigator.userAgent || '';
    return /iPad|iPhone|iPod/.test(ua) || (window.navigator.platform === 'MacIntel' && window.navigator.maxTouchPoints > 1);
  }

  // التثبيتُ الجديد على أندرويد والحاسوب: يُسجَّل في المتصفّح نفسِه فيشاركه التطبيقُ (المخزنُ واحد).
  window.addEventListener('appinstalled', mark);

  if (read() === VERSION || !inApp()) return;
  if (storageIsEmpty()) { mark(); return; } // iOS: تثبيتٌ جديدٌ بمخزنٍ فارغ — أيقونتُه جديدة

  var notice = document.getElementById('icon-update-notice');
  if (!notice) return; // صفحةٌ بلا بطاقة (الدخول مثلاً): لا تُحسم العلامةُ هنا، فقد يكون تثبيتاً قديماً انتهت جلستُه

  var ios = isIos();
  Array.prototype.forEach.call(notice.querySelectorAll('[data-icon-notice]'), function (part) {
    part.hidden = (part.getAttribute('data-icon-notice') === 'ios') !== ios;
  });
  var close = notice.querySelector('[data-icon-notice-dismiss]');
  if (close) {
    close.addEventListener('click', function () {
      notice.hidden = true;
      mark();
    });
  }
  notice.hidden = false;
})();

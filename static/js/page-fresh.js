/* عمرُ بيانات الصفحة وتحديثُها (W-20261012-014، قرارُ المالك D-410م، وW-20261124-008).
 *
 * من ترك تبويباً مفتوحاً يرى بياناتِ لحظةِ الفتح. فهنا مؤشّرُ «آخر تحديث hh:mm» وزرُّ تحديثٍ في المحتوى المشترك (base.html).
 * لا إعادةَ تحميلٍ تلقائيّةً أبداً: من يعود إلى تبويبٍ غاب أكثرَ من دقيقتين (120 ثانية، بحدث visibilitychange) يرى المؤشّرَ
 * وقد صار «بيانات منذ hh:mm — حدّث»، وزرُّ التحديث بارزاً (صنفُ المنصّة btn-warning بدل btn-ghost). ويُعلَن ذلك مرّةً
 * واحدةً لقارئات الشاشة بـaria-live تُزال بعد التحديث. والتحديثُ بضغطة المستخدم وحده.
 *
 * - الوقتُ بساعة الخادم: إزاحةٌ تُحسب عند التحميل من `data-now` (ثوانٍ) فلا يخدع المؤشّرَ ضبطُ ساعة الجهاز، ويُعرض بتوقيت الدوحة.
 * - لا علامةَ قِدَمٍ على الصفحة الحيّة: `[data-live-url]` أو `[data-director-live]` أو `[data-quiet-poll]` أو عنصرُ `hx-trigger` فيه every،
 *   لأنها تتحدّث بالاستطلاع وتُعلِم المؤشّرَ بحدث `page-live:updated`.
 * - تُزال العلامةُ بعد التحديث اليدويّ (إعادةُ التحميل) وبعد التبديل بـpage-nav (حدثُ `htmx:afterSwap` بـ`detail.pageNav`)،
 *   فيُصفَّر العمرُ ويُعاد حسابُ الاستثناء.
 * - الزرُّ اليدويّ يسأل أولاً إن كان في الصفحة ما قد يضيع: تعديلٌ غيرُ محفوظ أو مسوّدةٌ محفوظة (`data-draft-key`) أو `[data-no-fresh]`.
 * - يُخفى المؤشّرُ ولا يُعلَّم شيءٌ في: الإدارة ولوحة القيادة ومركز التصدير والواجهات البرمجيّة وصفحات الدخول.
 * - التحديثُ `location.reload()`: التبديلُ بـpage-nav.js لا يُعرَض واجهةً، والإعادةُ تحفظ موضعَ التمرير في المتصفّح ولا تكسر سكربتاتِ الصفحة.
 */
(function () {
  "use strict";

  var box = document.querySelector("[data-page-fresh]");
  if (!box) { return; }

  var HIDDEN_LIMIT_MS = 120 * 1000;
  var EXCLUDED = /^\/(admin|command-center|exports|api|auth|static|media)(\/|$)/;
  var CONFIRM_TEXT = "في الصفحة تعديلاتٌ غيرُ محفوظة قد تضيع بالتحديث. هل تريد التحديث؟";
  var LIVE_SELECTORS = ["[data-live-url]", "[data-director-live]", "[data-quiet-poll]", "[hx-trigger*=\"every\"]"];
  var FRESH_CLASS = "btn-ghost";
  var STALE_CLASS = "btn-warning";
  var LEAD_FRESH = "آخر تحديث ";
  var LEAD_STALE = "بيانات منذ ";
  var TAIL_STALE = " — حدّث";

  var timeNode = box.querySelector("[data-fresh-time]");
  var button = box.querySelector("[data-fresh-refresh]");
  // نصُّ «آخر تحديث» قبل الوقت، ونصُّ «— حدّث» بعده: عقدتا نصٍّ تُبدَّل قيمتهما فلا تُحذَف عقدةٌ ولا تُضاف مرّتين.
  var lead = timeNode && timeNode.previousSibling && timeNode.previousSibling.nodeType === 3 ? timeNode.previousSibling : null;
  var tail = null;
  if (timeNode && timeNode.parentNode) {
    tail = document.createTextNode("");
    timeNode.parentNode.insertBefore(tail, timeNode.nextSibling);
  }
  var serverNow = Number(box.getAttribute("data-now")) * 1000;
  var offset = isNaN(serverNow) || !serverNow ? 0 : serverNow - Date.now();
  var hiddenAt = 0;
  var dirty = false;
  var stale = false;
  var dataAt = 0;

  var formatter = null;
  try {
    formatter = new Intl.DateTimeFormat("en-GB", { hour: "2-digit", minute: "2-digit", hour12: false, timeZone: "Asia/Qatar" });
  } catch (e) { /* بلا Intl: يبقى وقتُ الخادم المرسوم */ }

  function now() { return Date.now() + offset; }

  // لحظةُ البيانات الحاليّة: كلُّ تحميلٍ أو تحديثٍ من الاستطلاع يضبطها.
  function stamp() {
    dataAt = now();
    if (timeNode && formatter) { timeNode.textContent = formatter.format(new Date(dataAt)); }
  }

  function excluded() { return EXCLUDED.test(location.pathname); }

  function main() { return document.getElementById("main-content"); }

  function isLive() {
    var root = main();
    if (!root) { return false; }
    return LIVE_SELECTORS.some(function (sel) { return !!root.querySelector(sel); });
  }

  function hasDraft() {
    var root = main();
    var holder = root && root.querySelector("[data-draft-key]");
    if (!holder) { return false; }
    try {
      var raw = window.localStorage.getItem(holder.getAttribute("data-draft-key"));
      return !!raw && raw !== "{}" && raw !== "null";
    } catch (e) { return false; }
  }

  function canLeave() {
    var root = main();
    return !(dirty || hasDraft() || (root && root.querySelector("[data-no-fresh]")));
  }

  // تبديلُ النصّ وصنفِ الزرّ معاً: البارزُ للقِدَم والعاديُّ للحداثة.
  function setLabel(on) {
    if (lead) { lead.nodeValue = on ? LEAD_STALE : LEAD_FRESH; }
    if (tail) { tail.nodeValue = on ? TAIL_STALE : ""; }
    if (button) {
      button.classList.remove(on ? FRESH_CLASS : STALE_CLASS);
      button.classList.add(on ? STALE_CLASS : FRESH_CLASS);
    }
  }

  // يُعلَّم المؤشّرُ بالقِدَم مرّةً واحدة: aria-live تُضاف قبل تغيير النصّ فيُعلَن مرّةً، ولا تُكرَّر عند عودةٍ أخرى.
  function markStale() {
    if (stale) { return; }
    stale = true;
    box.setAttribute("aria-live", "polite");
    setLabel(true);
  }

  function clearStale() {
    if (!stale) { return; }
    stale = false;
    box.removeAttribute("aria-live");
    setLabel(false);
  }

  function sync() {
    box.hidden = excluded();
    dirty = false;
    clearStale();
    stamp();
  }

  // أيُّ إدخالٍ داخل المحتوى يجعل الصفحةَ «قذرة» حتى تُبدَّل.
  document.addEventListener("input", function (event) {
    var root = main();
    if (root && event.target && root.contains(event.target)) { dirty = true; }
  }, true);

  document.addEventListener("visibilitychange", function () {
    if (document.hidden) {
      hiddenAt = Date.now();
      return;
    }
    var away = hiddenAt ? Date.now() - hiddenAt : 0;
    hiddenAt = 0;
    // لا تحديثَ تلقائيّاً أبداً: المؤشّرُ يُعلَّم بالقِدَم فقط، والتحديثُ بضغطة المستخدم.
    if (away > HIDDEN_LIMIT_MS && !excluded() && !isLive()) { markStale(); }
  });

  if (button) {
    var gate = box.querySelector("[data-fresh-gate]");
    // التأكيدُ بنافذة المنصّة (`data-confirm` في base.js) لا بحوارٍ أصليّ: الطلبُ الأوّلُ يعترضه base.js ويعرض النافذة،
    // وبعد «تأكيد» يعيد إرسالَ النموذج وعلى `_confirmed` فنُحدّث هنا.
    if (gate) {
      gate.addEventListener("submit", function (event) {
        if (gate._confirmed) { event.preventDefault(); window.location.reload(); }
      });
    }
    button.addEventListener("click", function () {
      if (canLeave() || !gate) { window.location.reload(); return; }
      gate.setAttribute("data-confirm", CONFIRM_TEXT);
      gate.requestSubmit();
    });
  }

  document.addEventListener("htmx:afterSwap", function (event) {
    if (event.detail && event.detail.pageNav) { sync(); }
  });

  // صفحةٌ حيّةٌ تتحدّث بالاستطلاع: يُحدَّث المؤشّرُ دون جلبٍ (W-20261012-015).
  document.addEventListener("page-live:updated", stamp);

  sync();
})();

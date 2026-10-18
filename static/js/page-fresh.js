/* عمرُ بيانات الصفحة وتحديثُها (W-20261012-014، قرارُ المالك D-410م).
 *
 * من ترك تبويباً مفتوحاً يرى بياناتِ لحظةِ الفتح بلا علامة. فهنا مؤشّرُ «آخر تحديث hh:mm» وزرُّ تحديثٍ في المحتوى المشترك (base.html)،
 * وتحديثٌ تلقائيٌّ حين يعود المستخدمُ إلى تبويبٍ غاب أكثرَ من دقيقتين (120 ثانية، بحدث visibilitychange).
 *
 * - الوقتُ بساعة الخادم: إزاحةٌ تُحسب عند التحميل من `data-now` (ثوانٍ) فلا يخدع المؤشّرَ ضبطُ ساعة الجهاز، ويُعرض بتوقيت الدوحة.
 * - لا تحديثَ تلقائيّاً على: صفحةٍ فيها إدخالٌ مُعدَّل أو مسوّدةٌ محفوظة (`data-draft-key` وفي localStorage شيء) أو `[data-no-fresh]`،
 *   ولا على صفحةٍ حيّةٍ (`[data-live-url]` أو `[data-director-live]`) لأنها تتحدّث بالاستطلاع وتُعلِم المؤشّرَ بحدث `page-live:updated`.
 * - الزرُّ اليدويّ يسأل أولاً إن كان في الصفحة ما قد يضيع.
 * - يُخفى المؤشّرُ ولا يُحدَّث شيءٌ في: الإدارة ولوحة القيادة ومركز التصدير والواجهات البرمجيّة وصفحات الدخول.
 * - التحديثُ `location.reload()`: التبديلُ بـpage-nav.js لا يُعرَض واجهةً، والإعادةُ تحفظ موضعَ التمرير في المتصفّح ولا تكسر سكربتاتِ الصفحة.
 * - الصفحةُ تُبدَّل بـpage-nav (حدثُ `htmx:afterSwap` بـ`detail.pageNav`) فيُصفَّر العمرُ ويُعاد حسابُ الاستثناء.
 */
(function () {
  "use strict";

  var box = document.querySelector("[data-page-fresh]");
  if (!box) { return; }

  var HIDDEN_LIMIT_MS = 120 * 1000;
  var EXCLUDED = /^\/(admin|command-center|exports|api|auth|static|media)(\/|$)/;
  var CONFIRM_TEXT = "في الصفحة تعديلاتٌ غيرُ محفوظة قد تضيع بالتحديث. هل تريد التحديث؟";

  var timeNode = box.querySelector("[data-fresh-time]");
  var button = box.querySelector("[data-fresh-refresh]");
  var serverNow = Number(box.getAttribute("data-now")) * 1000;
  var offset = isNaN(serverNow) || !serverNow ? 0 : serverNow - Date.now();
  var hiddenAt = 0;
  var dirty = false;

  var formatter = null;
  try {
    formatter = new Intl.DateTimeFormat("en-GB", { hour: "2-digit", minute: "2-digit", hour12: false, timeZone: "Asia/Qatar" });
  } catch (e) { /* بلا Intl: يبقى وقتُ الخادم المرسوم */ }

  function now() { return Date.now() + offset; }

  function stamp() {
    if (timeNode && formatter) { timeNode.textContent = formatter.format(new Date(now())); }
  }

  function excluded() { return EXCLUDED.test(location.pathname); }

  function main() { return document.getElementById("main-content"); }

  function isLive() {
    var root = main();
    return !!(root && root.querySelector("[data-live-url], [data-director-live]"));
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

  function sync() {
    box.hidden = excluded();
    dirty = false;
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
    if (away <= HIDDEN_LIMIT_MS || excluded() || isLive() || !canLeave()) { return; }
    window.location.reload();
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

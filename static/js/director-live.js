/* تحديثُ لوحة المدير حيّاً (W-20261008-004، D-249م القسم 9): استطلاعٌ دوريٌّ لنقطة JSON خفيفة بلا أسماء.
 *
 * - لا بناءَ DOM: تُبدَّل النصوصُ بـtextContent على عناصر `data-key` ("<نطاق>.<حقل>")؛ فلا HTML قادمٌ من الخادم يُحقن.
 * - الفاصلُ من الخادم (`next_in`، 45 ث) مع تشويشٍ ±5 ث كي لا تتزامن الطلبات؛ وتراجعٌ أسّيٌّ حتى 300 ث بعد الإخفاق.
 * - يتوقّف: عند إخفاء التبويب (ويُستأنف بجلبٍ فوريّ)، وعند `phase = final` (أوّلُ استجابةٍ بعد 14:00 بتوقيت الدوحة تحمل حكمَ اليوم)،
 *   وعند `closed` (يومٌ بلا دوام)، وعند 403 (لا إعادةَ محاولةٍ على الصلاحيّة). والتعديلُ بعد 14:00 يراه من يحدّث الصفحة.
 * - الصفحةُ المرسومةُ قبل 14:00 تُعاد تحميلاً مرّةً واحدةً حين تصير الاستجابةُ `final` (عناوينُ البطاقات تتغيّر بتغيّر الطور).
 */
(function () {
  "use strict";

  var root = document.querySelector("[data-director-live]");
  if (!root) { return; }

  var SCHEMA = 1;
  var DEFAULT_SECONDS = 45;
  var JITTER_SECONDS = 5;
  var MAX_BACKOFF_SECONDS = 300;
  var FAILURES_BEFORE_NOTICE = 3;
  // الصفحةُ التي رُسمت بالحكم النهائيّ لا تستطلع: لا يتغيّر شيءٌ بعد 14:00 (التعديلُ بتحديث الصفحة).
  if (root.getAttribute("data-phase") !== "live") { return; }

  var url = root.getAttribute("data-live-url");
  var seconds = DEFAULT_SECONDS;
  var failures = 0;
  var timer = null;
  var inflight = false;
  var stopped = false;

  function setText(key, value) {
    var nodes = root.querySelectorAll('[data-key="' + key + '"]');
    Array.prototype.forEach.call(nodes, function (node) {
      var text = String(value);
      if (node.textContent !== text) { node.textContent = text; }
    });
  }

  var SECTION_FIELDS = ["recorded", "state_label", "absent_unexcused", "early_absent", "away_permitted", "exit_minutes"];
  var STATE_BADGES = ["status-success", "status-warning", "status-danger", "status-gray"];

  function badgeClass(section) {
    if (section.state === "complete") { return "status-success"; }
    if (section.state === "partial") { return "status-warning"; }
    return section.gap ? "status-danger" : "status-gray";
  }

  function applySection(section) {
    SECTION_FIELDS.forEach(function (name) { setText("section." + section.id + "." + name, section[name]); });
    var badge = root.querySelector('[data-key="section.' + section.id + '.state_label"]');
    if (badge) {
      STATE_BADGES.forEach(function (name) { badge.classList.toggle(name, name === badgeClass(section)); });
    }
  }

  function apply(payload) {
    if (!payload || payload.schema !== SCHEMA || !payload.school) { throw new Error("schema"); }
    var school = payload.school;
    Object.keys(school).forEach(function (field) { setText("school." + field, school[field]); });
    if (payload.exits) { setText("exits.students", payload.exits.students); }
    // لوحةُ المشرف: صفُّ كلّ شعبةٍ بمفاتيح `section.<id>.<حقل>` — الأرقامُ والنصوصُ بـtextContent وشارةُ الحالة بصنف الهويّة المركزيّ.
    (payload.sections || []).forEach(applySection);
    if (payload.next_in) { seconds = Number(payload.next_in) || DEFAULT_SECONDS; }
    if (payload.phase === "final") {
      stopped = true;
      window.location.reload();
    } else if (payload.phase === "closed") {
      stopped = true;
    }
  }

  function delay() {
    var jitter = (Math.random() * 2 - 1) * JITTER_SECONDS;
    return Math.min(MAX_BACKOFF_SECONDS, (seconds + jitter) * Math.pow(2, failures)) * 1000;
  }

  function schedule() {
    window.clearTimeout(timer);
    if (stopped || document.hidden) { return; }
    timer = window.setTimeout(poll, delay());
  }

  function notice(text) {
    var line = root.querySelector("[data-live-note]");
    if (line) { line.textContent = text; line.hidden = !text; }
  }

  function poll() {
    if (inflight || stopped) { return; }
    inflight = true;
    window.fetch(url, { credentials: "same-origin", headers: { Accept: "application/json" } })
      .then(function (response) {
        if (response.status === 403) { stopped = true; throw new Error("forbidden"); }
        var type = response.headers.get("Content-Type") || "";
        if (!response.ok || type.indexOf("application/json") === -1) { throw new Error("not-json"); }
        return response.json();
      })
      .then(function (payload) {
        apply(payload);
        failures = 0;
        notice("");
      })
      .catch(function (error) {
        failures += 1;
        if (error && error.message === "schema") {
          notice("تغيّر إصدارُ العقد — حدِّث الصفحة.");
        } else if (failures >= FAILURES_BEFORE_NOTICE && !stopped) {
          notice("انقطع الاتصال — تُعرض آخرُ أرقامٍ وصلت.");
        }
      })
      .then(function () {
        inflight = false;
        schedule();
      });
  }

  document.addEventListener("visibilitychange", function () {
    if (document.hidden) { window.clearTimeout(timer); } else { poll(); }
  });
  schedule();
})();

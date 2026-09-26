/* مركز قيادة الجودة — استطلاعُ اللقطة وتحديثُ اللوحات (عقدُ اللقطة v1: command_center/contract.py).
 *
 * لا بناءَ DOM: تُبدَّل النصوصُ بـtextContent على عقدٍ مفاتيحُها data-key ("<لوحة>.<حقل>") والحالةُ بصنفٍ
 * qc-panel--<حالة>؛ فلا HTML قادمٌ من الخادم يُحقن، ولا يُحرَّك ما يراقبه admin_a11y.js.
 * الاستطلاعُ يتوقّف عند إخفاء التبويب ويستأنف بجلبٍ فوريّ؛ وردٌّ غيرُ JSON (تحويلٌ لصفحة الدخول أو /offline/)
 * = «انتهت الجلسة» بعد ثلاثة إخفاقاتٍ متتالية، مع تراجعٍ أسّيٍّ في الفواصل. والـWebSocket لاحقاً.
 */
(function () {
  "use strict";

  var root = document.querySelector("[data-qc-url]");
  if (!root) { return; }

  var SCHEMA = Number(root.getAttribute("data-qc-schema")) || 1;
  var MIN_SECONDS = 15;
  var MAX_SECONDS = 60;
  var FAILURES_BEFORE_NOTICE = 3;
  var MAX_BACKOFF_SECONDS = 300;
  var STATE_LABEL = { ok: "سليم", warn: "انتبه", bad: "خطر", unknown: "غير معلوم" };
  var STATUSES = ["ok", "warn", "bad", "unknown"];

  var url = root.getAttribute("data-qc-url");
  var note = root.querySelector("[data-qc-note]");
  var clock = root.querySelector('[data-key="generated"]');
  var button = root.querySelector("[data-qc-refresh]");
  var panels = Array.prototype.slice.call(root.querySelectorAll("[data-panel]"));
  var failures = 0;
  var timer = null;
  var inflight = false;

  function baseSeconds() {
    var smallest = MAX_SECONDS;
    panels.forEach(function (panel) {
      var seconds = Number(panel.getAttribute("data-refresh")) || MAX_SECONDS;
      if (seconds < smallest) { smallest = seconds; }
    });
    return Math.min(MAX_SECONDS, Math.max(MIN_SECONDS, smallest));
  }

  function setText(scope, key, text) {
    var node = scope.querySelector('[data-key="' + key + '"]');
    if (node && node.textContent !== text) { node.textContent = text; }
  }

  function ageText(seconds) {
    if (seconds === null || seconds === undefined) { return "لم يُجمَع بعدُ"; }
    if (seconds < 90) { return "قبل لحظات"; }
    if (seconds < 5400) { return "قبل " + Math.round(seconds / 60) + " دقيقة"; }
    return "قبل " + Math.round(seconds / 3600) + " ساعة";
  }

  function showNote(text) {
    if (!note) { return; }
    note.textContent = text;
    note.hidden = !text;
  }

  function paint(panel, data) {
    var status = STATUSES.indexOf(data.status) === -1 ? "unknown" : data.status;
    var previous = panel.getAttribute("data-status");
    STATUSES.forEach(function (name) { panel.classList.toggle("qc-panel--" + name, name === status); });
    panel.setAttribute("data-status", status);
    var key = data.key;
    setText(panel, key + ".state", STATE_LABEL[status]);
    setText(panel, key + ".headline", String(data.headline || "") || "لم يُجمَع بعدُ");
    setText(panel, key + ".detail", String(data.detail || ""));
    setText(panel, key + ".age", ageText(data.age_seconds));
    // يُعلن قارئُ الشاشة الانتقالَ إلى الأحمر وحدَه، لا كلَّ استطلاعٍ (تنبيهٌ عند الأحمر فقط)
    if (status === "bad" && previous && previous !== "bad") {
      showNote("صارت لوحة «" + String(data.title || key) + "» في حالة خطر.");
    }
  }

  function apply(snapshot) {
    if (!snapshot || snapshot.schema !== SCHEMA || !Array.isArray(snapshot.panels)) {
      throw new Error("schema");
    }
    var byKey = {};
    snapshot.panels.forEach(function (data) { byKey[data.key] = data; });
    panels.forEach(function (panel) {
      var data = byKey[panel.getAttribute("data-panel")];
      if (data) { paint(panel, data); }
    });
    if (clock) {
      clock.textContent = "آخر تحديث " + new Date(snapshot.generated_at * 1000).toLocaleTimeString("ar");
    }
  }

  function schedule() {
    window.clearTimeout(timer);
    if (document.hidden) { return; }
    var seconds = Math.min(MAX_BACKOFF_SECONDS, baseSeconds() * Math.pow(2, failures));
    timer = window.setTimeout(poll, seconds * 1000);
  }

  function fail(error) {
    failures += 1;
    if (error && error.message === "schema") {
      showNote("تغيّر إصدارُ عقد اللقطة — حدِّث الصفحة لتحميل الإصدار الجديد.");
    } else if (failures >= FAILURES_BEFORE_NOTICE) {
      showNote("انتهت الجلسة أو انقطع الاتصال — حدِّث الصفحة أو سجّل الدخول من جديد.");
    }
  }

  function poll() {
    if (inflight) { return; }
    inflight = true;
    window.fetch(url, { credentials: "same-origin", headers: { Accept: "application/json" } })
      .then(function (response) {
        var type = response.headers.get("Content-Type") || "";
        if (!response.ok || type.indexOf("application/json") === -1) { throw new Error("not-json"); }
        return response.json();
      })
      .then(function (snapshot) {
        apply(snapshot);
        failures = 0;
        showNote("");
      })
      .catch(fail)
      .then(function () {
        inflight = false;
        schedule();
      });
  }

  document.addEventListener("visibilitychange", function () {
    if (document.hidden) { window.clearTimeout(timer); } else { poll(); }
  });
  if (button) { button.addEventListener("click", poll); }

  panels.forEach(function (panel) {
    panel.setAttribute("data-status", STATUSES.filter(function (name) {
      return panel.classList.contains("qc-panel--" + name);
    })[0] || "unknown");
  });
  poll();
})();

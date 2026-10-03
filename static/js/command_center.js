/* مركز قيادة الجودة — استطلاعُ اللقطة وتحديثُ اللوحات (عقدُ اللقطة v1: command_center/contract.py).
 *
 * لا بناءَ DOM: تُبدَّل النصوصُ بـtextContent على عقدٍ مفاتيحُها data-key ("<لوحة>.<حقل>") والحالةُ بصنفٍ
 * is-<حالة> على عنصر اللوحة؛ فلا HTML قادمٌ من الخادم يُحقن. والصفحةُ في المنصّة (لا /admin/) — QCC-01b.
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
  // الحالةُ نصّاً ورمزاً لا لوناً وحدَه — وتطابق command_center/layout.py:STATE_LABELS (يحرسه اختبار)
  var STATE_LABEL = { ok: "✔ سليم", warn: "▲ انتبه", bad: "✖ خطر", unknown: "؟ غير معلوم" };
  var STATUSES = ["ok", "warn", "bad", "unknown"];
  var ORDER = ["bad", "warn", "unknown", "ok"];   // الأخطرُ أوّلاً — لاختيار أسوأ حالات المجموعة
  var METRIC_SLOTS = 4;

  var url = root.getAttribute("data-qc-url");
  var note = root.querySelector("[data-qc-note]");
  var noteText = root.querySelector("[data-qc-note-text]");
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

  function setText(scope, key, text, withTitle) {
    var node = scope.querySelector('[data-key="' + key + '"]');
    if (!node) { return; }
    if (node.textContent !== text) { node.textContent = text; }
    // العنوانُ الكاملُ في title لعنصرٍ يقصّه line-clamp (1.4.12) — يُزامَن معه لا يُكتب مرّةً عند الرسم فيَبلى.
    if (withTitle && node.title !== text) { node.title = text; }
  }

  function ageText(seconds) {
    if (seconds === null || seconds === undefined) { return "لم يُجمَع بعدُ"; }
    if (seconds < 90) { return "قبل لحظات"; }
    if (seconds < 5400) { return "قبل " + Math.round(seconds / 60) + " دقيقة"; }
    return "قبل " + Math.round(seconds / 3600) + " ساعة";
  }

  function showNote(text) {
    if (!note || !noteText) { return; }
    noteText.textContent = text;
    note.hidden = !text;
  }

  // بارُ قراءة اللوحة (0–100، 100 أسلم) بمكوّن الهويّة `progress-qatar`: متغيّرُ CSS `--progress-w` وصنفُ النبرة `pf-*` — لا بناءَ DOM ولا لونَ محلّيّ؛
  // وبلا قراءةٍ يعود إلى 0 بنصٍّ بديلٍ «لم تُجمَع بعدُ».
  var BAR_TONE = { ok: "pf-success", warn: "pf-warning", bad: "pf-danger", unknown: "" };
  var BADGE = { ok: "status-success", warn: "status-warning", bad: "status-danger", unknown: "status-gray" };

  function paintBar(panel, gauge, status) {
    var bar = panel.querySelector("[data-bar]");
    if (!bar) { return; }
    var value = gauge === null || gauge === undefined || gauge === "" || isNaN(Number(gauge)) ? null : Math.max(0, Math.min(100, Math.round(Number(gauge))));
    var fill = bar.querySelector(".progress-qatar-fill");
    if (fill) {
      fill.style.setProperty("--progress-w", (value === null ? 0 : value) + "%");
      Object.keys(BAR_TONE).forEach(function (name) {
        if (BAR_TONE[name]) { fill.classList.toggle(BAR_TONE[name], name === status); }
      });
    }
    bar.setAttribute("aria-valuenow", String(value === null ? 0 : value));
    if (value === null) { bar.setAttribute("aria-valuetext", "لم تُجمَع بعدُ"); } else { bar.removeAttribute("aria-valuetext"); }
  }

  // شارةُ الحالة بصنف الهويّة المركزيّ `status-*` (والنصُّ والرمزُ يبقيان: لا لونٌ وحدَه).
  function paintBadge(panel, key, status) {
    var badge = panel.querySelector('[data-key="' + key + '.state"]');
    if (!badge) { return; }
    Object.keys(BADGE).forEach(function (name) { badge.classList.toggle(BADGE[name], name === status); });
  }

  function paintMetrics(panel, key, metrics) {
    var list = Array.isArray(metrics) ? metrics : [];
    var featured = Number(panel.getAttribute("data-featured")) || 0;
    for (var index = 1; index <= METRIC_SLOTS; index += 1) {
      var metric = list[index - 1];
      var row = panel.querySelector('[data-row="' + key + ".m" + index + '"]');
      if (row) { row.hidden = !metric; }
      setText(panel, key + ".m" + index + "l", metric ? String(metric.label) : "");
      // الرقمُ الكبير بلا قراءةٍ يعرض «؟» لا فراغاً (لا يُوهَم سليماً)
      setText(panel, key + ".m" + index + "v", metric ? String(metric.value) : (index === featured ? "؟" : ""));
    }
  }

  function paint(panel, data) {
    var status = STATUSES.indexOf(data.status) === -1 ? "unknown" : data.status;
    var previous = panel.getAttribute("data-status");
    STATUSES.forEach(function (name) { panel.classList.toggle("is-" + name, name === status); });
    panel.setAttribute("data-status", status);
    var key = data.key;
    setText(panel, key + ".state", STATE_LABEL[status]);
    setText(root, key + ".pstate", STATE_LABEL[status]);
    setText(panel, key + ".headline", String(data.headline || "") || "لم يُجمَع بعدُ", true);
    setText(panel, key + ".detail", String(data.detail || ""));
    setText(panel, key + ".age", ageText(data.age_seconds));
    paintBar(panel, data.gauge, status);
    paintBadge(panel, key, status);
    paintMetrics(panel, key, data.metrics);
    // يُعلن قارئُ الشاشة الانتقالَ إلى الأحمر وحدَه، لا كلَّ استطلاعٍ (تنبيهٌ عند الأحمر فقط)
    if (status === "bad" && previous && previous !== "bad") {
      showNote("صارت لوحة «" + String(data.title || key) + "» في حالة خطر.");
    }
  }

  // شريطُ «ما ينتظرك الآن» ورؤوسُ المجموعات من اللقطة نفسِها — ما يراه الخادمُ وحدَه (يطابق command_center/layout.py:strip وgroups).
  function paintSummary(list) {
    var reds = [];
    var warns = 0;
    var unknown = 0;
    var unpublished = null;
    list.forEach(function (data) {
      if (data.status === "bad") { reds.push(String(data.title || data.key)); }
      else if (data.status === "warn") { warns += 1; }
      else if (STATUSES.indexOf(data.status) === -1 || data.status === "unknown") { unknown += 1; }
      if (data.key === "pulls" && Array.isArray(data.metrics)) {
        data.metrics.forEach(function (metric) {
          if (metric.label === "إيداعاتٌ غيرُ منشورة") { unpublished = String(metric.value); }
        });
      }
    });
    setText(root, "strip.reds", reds.length ? "✖ خطر: " + reds.join("، ") : "✔ لا لوحةَ في حالة خطر");
    setText(root, "strip.bad", String(reds.length));
    setText(root, "strip.warn", String(warns));
    setText(root, "strip.unknown", String(unknown));
    setText(root, "strip.unpublished", unpublished === null ? "؟" : unpublished);
    var byKey = {};
    list.forEach(function (data) { byKey[data.key] = data; });
    Array.prototype.forEach.call(root.querySelectorAll("[data-group]"), function (group) {
      var members = Array.prototype.slice.call(group.querySelectorAll("[data-panel]"));
      var worst = "ok";
      var ok = 0;
      members.forEach(function (member) {
        var data = byKey[member.getAttribute("data-panel")];
        var status = data && STATUSES.indexOf(data.status) !== -1 ? data.status : "unknown";
        if (status === "ok") { ok += 1; }
        if (ORDER.indexOf(status) < ORDER.indexOf(worst)) { worst = status; }
      });
      setText(group, "group." + group.getAttribute("data-group") + ".state",
        STATE_LABEL[worst] + " · " + ok + " من " + members.length + " سليمة");
    });
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
    paintSummary(snapshot.panels);
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
      return panel.classList.contains("is-" + name);
    })[0] || "unknown");
  });
  poll();
})();

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
  // تفضيلُ اللوحات المخفيّة: كوكي مفاتيحُه مفصولةٌ بفواصل؛ الخادمُ يقرؤه فيرسم المخفيَّ مخفيّاً (بلا وميض) ويتحقّق من المفاتيح.
  var HIDDEN_COOKIE = "qcc_hidden";
  var HIDDEN_MAX_AGE = 365 * 24 * 3600;

  var url = root.getAttribute("data-qc-url");
  var note = root.querySelector("[data-qc-note]");
  var noteText = root.querySelector("[data-qc-note-text]");
  var clock = root.querySelector('[data-key="generated"]');
  var button = root.querySelector("[data-qc-refresh]");
  var toggles = Array.prototype.slice.call(root.querySelectorAll("[data-qc-toggle]"));
  var counter = root.querySelector("[data-qc-count]");
  var none = root.querySelector("[data-qc-none]");
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
    setText(root, "strip.counts", "▲ انتبه: " + warns + " · ؟ غير معلوم: " + unknown);
    setText(root, "strip.unpublished", "الإيداعاتُ غيرُ المنشورة: " + (unpublished === null ? "غيرُ معلومة" : unpublished));
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

  function saveHidden(keys) {
    var secure = window.location.protocol === "https:" ? "; Secure" : "";
    document.cookie = HIDDEN_COOKIE + "=" + keys.join(",") + "; Path=/command-center/; Max-Age=" +
      (keys.length ? HIDDEN_MAX_AGE : 0) + "; SameSite=Lax" + secure;
  }

  // يطبّق اختيارَ المربّعات: يُظهر ويُخفي بطاقاتِ اللوحات، ويحدّث العدّادَ ورسالةَ «كلُّها مخفيّة»، ويحفظ التفضيل.
  function applyChoices(save) {
    var hidden = [];
    toggles.forEach(function (box) {
      var key = box.getAttribute("data-qc-toggle");
      var card = root.querySelector('[data-card="' + key + '"]');
      if (card) { card.hidden = !box.checked; }
      if (!box.checked) { hidden.push(key); }
    });
    // مجموعةٌ كلُّ لوحاتها مخفيّةٌ تُخفى كاملةً (رأسُها أيضاً)
    Array.prototype.forEach.call(root.querySelectorAll("[data-group]"), function (group) {
      var cards = Array.prototype.slice.call(group.querySelectorAll("[data-card]"));
      group.hidden = cards.length > 0 && cards.every(function (card) { return card.hidden; });
    });
    var shown = toggles.length - hidden.length;
    if (counter) { counter.textContent = shown + " من " + toggles.length; }
    if (none) { none.hidden = shown > 0; }
    if (save) { saveHidden(hidden); }
  }

  toggles.forEach(function (box) {
    box.addEventListener("change", function () { applyChoices(true); });
  });
  Array.prototype.forEach.call(root.querySelectorAll("[data-qc-all]"), function (control) {
    control.addEventListener("click", function () {
      var show = control.getAttribute("data-qc-all") === "show";
      toggles.forEach(function (box) { box.checked = show; });
      applyChoices(true);
    });
  });

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

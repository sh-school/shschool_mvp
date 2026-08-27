/* ══════════════════════════════════════════════════════════════════
   actions.js — مفردات `data-*` معلنة بدل معالِجات الأحداث الداخلية
   ══════════════════════════════════════════════════════════════════

   سياسة أمن المحتوى تحمل `nonce` في `script-src`، ووجودُه يجعل المتصفّح
   يتجاهل `'unsafe-inline'` تماماً — فتُحجب سمات `onclick` و`onchange`
   وأمثالها، ولا ينفعها nonce لأنها سمات لا وسوم.

   والبديل ليس نقل كل معالِج إلى سكربتٍ خاصّ به، بل مفرداتٌ معلنة يقرؤها
   مستمعٌ مفوَّض واحد على `document`. فالسلوك يبقى في السمة كما كان — مقروءاً
   بجانب العنصر — بلا شيفرةٍ قابلة للتنفيذ داخل الصفحة.

   ولا `eval` هنا ولا `new Function`: كل فعلٍ مُسمّى ومُنفَّذ بشيفرةٍ ثابتة.

   المفردات
   ────────
     data-autosubmit                 change  → يُرسل النموذج الحاضن
     data-action="print|reload|back|stop"
     data-confirm="نصّ"              submit  → يمنع الإرسال ما لم يُؤكَّد
     data-toggle="#sel"              click   → يقلب إخفاء الهدف (خاصية hidden)
     data-toggle-class="#sel|صنف"    click   → يقلب صنفاً على الهدف
     data-hide="#sel" / data-show="#sel"
     data-remove="#sel|closest:.sel" click   → يحذف الهدف
     data-click="#sel"               click   → ينقر الهدف نيابةً عنه
     data-copy="نصّ"                 click   → ينسخ إلى الحافظة
     data-call="اسم"                 click   → يُنادي دالّةً من قائمةٍ بيضاء
     data-arg="وسيط"                         → وسيطٌ واحد اختياريّ لـdata-call
     data-mirror="#sel"              input   → يعكس القيمة نصّاً في الهدف
   ══════════════════════════════════════════════════════════════════ */

(function () {
  "use strict";

  /* تحميلٌ مزدوج — صفحةٌ تُدرج الوحدة وترث قالباً يُدرجها كذلك — يعني تسجيل
     المستمعات مرّتين، فيُنفَّذ كل فعلٍ مرّتين: تأكيدان متتاليان، وقلبٌ يعود
     إلى ما كان. والحارس هنا يجعل الإدراج المكرّر بلا أثر. */
  if (window.__schoolosActionsBound) return;
  window.__schoolosActionsBound = true;

  /* الدوالّ المسموح استدعاؤها بالاسم. القائمة بيضاء لا سوداء: اسمٌ غير مذكور
     هنا لا يُنفَّذ — فلا تصير `data-call` باباً خلفياً لتنفيذٍ عشوائيّ. */
  var CALLABLE = [
    "closeModal",
    "toggleImportForm",
    "toggleForm",
    "toggleUpload",
    "onFileSelected",
    "fillJobTitle",
    "filterProcs",
    "applyFilter",
    "submitScheduleView",
    "installPWA",
    "showToast",
  ];

  function resolve(el, sel) {
    if (!sel) return null;
    if (sel.indexOf("closest:") === 0) return el.closest(sel.slice(8));
    return document.querySelector(sel);
  }

  function on(type, attr, fn) {
    document.addEventListener(
      type,
      function (e) {
        var el = e.target.closest ? e.target.closest("[" + attr + "]") : null;
        if (el) fn(el, e);
      },
      type === "submit" || type === "change" || type === "input",
    );
  }

  /* ── إرسالٌ تلقائيّ عند تغيّر حقل داخل نموذج ───────────────────── */
  on("change", "data-autosubmit", function (el) {
    if (el.form) el.form.submit();
  });

  /* ── تأكيدٌ قبل الإرسال ──────────────────────────────────────────
     تُقرأ من النموذج أو من الزرّ المُرسِل. الأصل أنها على `<form>` — إذ كانت
     `onsubmit` سمةَ نموذج — لكن وضعَها على زرٍّ تصرّفٌ متوقّع، وتركُه صامتاً
     يُعيد العطب الذي نُطارده: سلوكٌ مكتوبٌ لا يقع ولا يُبلّغ. */
  document.addEventListener(
    "submit",
    function (e) {
      var el = e.target.closest("[data-confirm]");
      if (!el && e.submitter && e.submitter.closest) {
        el = e.submitter.closest("[data-confirm]");
      }
      if (el && !window.confirm(el.getAttribute("data-confirm"))) e.preventDefault();
    },
    true,
  );

  /* ── أفعالٌ مُسمّاة بلا وسيط ────────────────────────────────────── */
  var ACTIONS = {
    print: function () {
      window.print();
    },
    reload: function () {
      window.location.reload();
    },
    back: function () {
      window.history.back();
    },
    stop: function (el, e) {
      e.stopPropagation();
    },
  };

  on("click", "data-action", function (el, e) {
    var fn = ACTIONS[el.getAttribute("data-action")];
    if (fn) fn(el, e);
  });

  /* ── إظهارٌ وإخفاءٌ وحذف ────────────────────────────────────────── */
  on("click", "data-toggle", function (el) {
    var t = resolve(el, el.getAttribute("data-toggle"));
    if (t) t.hidden = !t.hidden;
  });

  on("click", "data-hide", function (el) {
    var t = resolve(el, el.getAttribute("data-hide"));
    if (t) t.hidden = true;
  });

  on("click", "data-show", function (el) {
    var t = resolve(el, el.getAttribute("data-show"));
    if (t) t.hidden = false;
  });

  on("click", "data-remove", function (el) {
    var t = resolve(el, el.getAttribute("data-remove"));
    if (t) t.remove();
  });

  /* صيغة "#sel|صنف" — الهدف والصنف مفصولان بشَرطة رأسية. */
  on("click", "data-toggle-class", function (el) {
    var spec = el.getAttribute("data-toggle-class").split("|");
    var t = resolve(el, spec[0]);
    if (t && spec[1]) t.classList.toggle(spec[1]);
  });

  on("click", "data-click", function (el) {
    var t = resolve(el, el.getAttribute("data-click"));
    if (t) t.click();
  });

  /* ── الحافظة ───────────────────────────────────────────────────── */
  on("click", "data-copy", function (el) {
    if (navigator.clipboard) navigator.clipboard.writeText(el.getAttribute("data-copy"));
  });

  /* ── نداءٌ بالاسم من القائمة البيضاء ───────────────────────────── */
  on("click", "data-call", function (el) {
    var name = el.getAttribute("data-call");
    if (CALLABLE.indexOf(name) === -1) return;
    var fn = window[name];
    if (typeof fn !== "function") return;
    var arg = el.getAttribute("data-arg");
    fn(arg === null ? el : arg);
  });

  on("change", "data-call-change", function (el) {
    var name = el.getAttribute("data-call-change");
    if (CALLABLE.indexOf(name) === -1) return;
    var fn = window[name];
    if (typeof fn !== "function") return;
    /* `data-filter` يعني توقيعاً من وسيطين: (المفتاح، القيمة). */
    var key = el.getAttribute("data-filter");
    if (key !== null) fn(key, el.value);
    else fn(el);
  });

  /* ── عكسُ قيمة حقلٍ نصّاً ───────────────────────────────────────── */
  on("input", "data-mirror", function (el) {
    var t = resolve(el, el.getAttribute("data-mirror"));
    if (t) t.textContent = el.value;
  });

  on("input", "data-mirror-next", function (el) {
    if (el.nextElementSibling) el.nextElementSibling.textContent = el.value;
  });

  /* ── ضبط قيمة حقلٍ آخر: "#sel|قيمة" ────────────────────────────── */
  on("click", "data-set-value", function (el) {
    var spec = el.getAttribute("data-set-value").split("|");
    var t = resolve(el, spec[0]);
    if (t) t.value = spec.slice(1).join("|");
  });

  /* ── إغلاق نافذةٍ عائمة: ينادي closeModal إن وُجدت ثمّ يحذف الحاضن ── */
  on("click", "data-close-modal", function (el) {
    if (typeof window.closeModal === "function") window.closeModal();
    var t = resolve(el, el.getAttribute("data-close-modal") || "closest:.q-modal-overlay");
    if (t) t.remove();
  });

  /* ── الإغلاق بالنقر على الخلفية وحدها لا على محتواها ───────────── */
  on("click", "data-close-on-backdrop", function (el, e) {
    if (e.target !== el) return;
    if (typeof window.closeModal === "function") window.closeModal();
    el.remove();
  });

  /* ── قلبُ صنفٍ عند تغيّر مربّع اختيار: "#sel|صنف" ─────────────────
     يُقلَب وفق حالة المربّع لا بالتناوب، فيبقى متّسقاً مع ما يراه المستخدم. */
  on("change", "data-toggle-class-when", function (el) {
    var spec = el.getAttribute("data-toggle-class-when").split("|");
    var t = resolve(el, spec[0]);
    if (t && spec[1]) t.classList.toggle(spec[1], !el.checked);
  });

  /* ── عرض اسم الملفّ المختار ─────────────────────────────────────── */
  on("change", "data-file-name", function (el) {
    var spec = el.getAttribute("data-file-name").split("|");
    var t = resolve(el, spec[0]);
    if (!t) return;
    t.textContent = el.files && el.files[0] ? el.files[0].name : spec[1] || "";
  });

  /* ── إظهارُ حقلٍ حين تُطابق القيمة: "#sel|القيمة" ────────────────── */
  on("change", "data-show-when", function (el) {
    var spec = el.getAttribute("data-show-when").split("|");
    var t = resolve(el, spec[0]);
    if (t) t.hidden = el.value !== spec[1];
  });

  /* ── تنبيهٌ عائم: "نصّ|نوع" ─────────────────────────────────────── */
  on("click", "data-toast", function (el) {
    if (typeof window.showToast !== "function") return;
    var spec = el.getAttribute("data-toast").split("|");
    window.showToast(spec[0], spec[1] || "info");
  });

  /* ── تعطيلُ حقلٍ تبعاً لمربّع اختيار: "#sel" ─────────────────────── */
  on("change", "data-disables", function (el) {
    var t = resolve(el, el.getAttribute("data-disables"));
    if (!t) return;
    t.disabled = el.checked;
    t.style.opacity = el.checked ? "0.3" : "1";
  });
})();

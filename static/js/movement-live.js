/**
 * تحديثٌ هادئ للّوحة الحيّة في «تحركات الطلبة» (#movement-live) — بلا رمشٍ ولا فقدِ إدخالٍ ولا قفز.
 * - لا يُستبدل شيءٌ أثناء تفاعل المستخدم: تركيزٌ داخل select/input/textarea/زرّ نموذج، أو حقلٌ تغيّرت قيمته ولم تُحفظ،
 *   أو مؤشرُ فأرةٍ مضغوط. تُلغى الدورةُ في htmx:beforeRequest ويُتحقَّق ثانيةً في htmx:beforeSwap (قد يبدأ التفاعل أثناء الطلب).
 * - التبويبُ المخفيّ: تُلغى الدورة، ويُجلب مرّةً واحدةً عند العودة.
 * - بعد الاستبدال: يُستعاد تمريرُ الصفحة وتمريرُ كلّ table-wrap (أفقيًّا وعموديًّا) والتركيزُ إلى العنصر المقابل إن وُجد.
 * لا بياناتٍ شخصيّة تُقرأ أو تُخزَّن هنا.
 */
(function () {
  "use strict";
  var PANEL_ID = "movement-live";
  var FIELDS = "select, input, textarea";
  var FORM_BUTTONS = "form button, form input[type=submit], form input[type=button]";
  var pressed = false;
  var pendingFetch = false;
  var saved = null;

  function panel() { return document.getElementById(PANEL_ID); }

  function isPanelEvent(ev) {
    var el = panel();
    var target = ev && ev.detail && (ev.detail.target || ev.detail.elt);
    return !!el && !!target && (target === el || el.contains(target) || target.id === PANEL_ID);
  }

  // هل في اللوحة حقلٌ تغيّرت قيمته عن الأصل ولم يُحفظ؟
  function hasDirtyField(el) {
    var fields = el.querySelectorAll(FIELDS);
    for (var i = 0; i < fields.length; i++) {
      var f = fields[i];
      if (f.tagName === "SELECT") {
        for (var j = 0; j < f.options.length; j++) {
          if (f.options[j].selected !== f.options[j].defaultSelected) return true;
        }
      } else if (f.type === "checkbox" || f.type === "radio") {
        if (f.checked !== f.defaultChecked) return true;
      } else if (f.type !== "hidden" && f.value !== f.defaultValue) {
        return true;
      }
    }
    return false;
  }

  function isInteracting() {
    var el = panel();
    if (!el) return false;
    if (pressed) return true;
    var active = document.activeElement;
    if (active && el.contains(active) && active.matches && (active.matches(FIELDS) || active.matches(FORM_BUTTONS))) {
      return true;
    }
    return hasDirtyField(el);
  }

  function shouldHold() {
    return document.hidden || isInteracting();
  }

  // مفتاحُ العنصر المركَّز ليُعثر على مقابله بعد الاستبدال (رابطٌ أو زرُّ تبديل العرض).
  function focusSelector(active) {
    if (!active || !active.getAttribute) return null;
    var href = active.getAttribute("href");
    if (href) return 'a[href="' + href.replace(/"/g, '\\"') + '"]';
    var view = active.getAttribute("data-movement-view-btn");
    if (view) return '[data-movement-view-btn="' + view + '"]';
    return null;
  }

  function capture(el) {
    var wraps = [];
    el.querySelectorAll(".table-wrap").forEach(function (w) {
      wraps.push([w.scrollLeft, w.scrollTop]);
    });
    var active = document.activeElement;
    saved = {
      x: window.scrollX,
      y: window.scrollY,
      wraps: wraps,
      focus: active && el.contains(active) ? focusSelector(active) : null,
    };
  }

  function restore() {
    var snap = saved;
    saved = null;
    var el = panel();
    if (!snap || !el) return;
    el.querySelectorAll(".table-wrap").forEach(function (w, i) {
      if (snap.wraps[i]) {
        w.scrollLeft = snap.wraps[i][0];
        w.scrollTop = snap.wraps[i][1];
      }
    });
    if (snap.focus) {
      var next = el.querySelector(snap.focus);
      if (next && next.focus) next.focus({ preventScroll: true });
    }
    if (window.scrollX !== snap.x || window.scrollY !== snap.y) window.scrollTo(snap.x, snap.y);
  }

  document.addEventListener("pointerdown", function () { pressed = true; });
  ["pointerup", "pointercancel", "dragend"].forEach(function (name) {
    document.addEventListener(name, function () { pressed = false; }, true);
  });
  window.addEventListener("blur", function () { pressed = false; });

  document.addEventListener("htmx:beforeRequest", function (ev) {
    if (!isPanelEvent(ev)) return;
    if (document.hidden) pendingFetch = true;
    if (shouldHold()) ev.preventDefault();
  });

  document.addEventListener("htmx:beforeSwap", function (ev) {
    if (!isPanelEvent(ev)) return;
    if (shouldHold()) {
      ev.detail.shouldSwap = false;
      if (document.hidden) pendingFetch = true;
      return;
    }
    capture(ev.detail.target);
  });

  document.addEventListener("htmx:afterSwap", function (ev) {
    if (isPanelEvent(ev) || saved) restore();
  });

  // العودةُ إلى التبويب: جلبةٌ واحدة إن فاتت دورةٌ أثناء الإخفاء.
  document.addEventListener("visibilitychange", function () {
    if (document.hidden || !pendingFetch) return;
    pendingFetch = false;
    var el = panel();
    var url = el && el.getAttribute("hx-get");
    if (!url || !window.htmx || isInteracting()) return;
    window.htmx.ajax("GET", url, { target: "#" + PANEL_ID, swap: "outerHTML" });
  });
})();

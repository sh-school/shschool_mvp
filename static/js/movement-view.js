/**
 * تبديلُ عرضِ اللوحة الحيّة (تحركات الطلبة) بين جدولٍ وبطاقات.
 * - الاختيارُ يُحفظ في localStorage (قيمةٌ واحدة: table أو cards، بلا بياناتٍ شخصيّة) ويُوضع على `html[data-movement-view]`.
 * - بلا اختيارٍ محفوظ يقرّر CSS: بطاقاتٌ على الجوال وجدولٌ على الواسع.
 * - الأزرارُ داخل الجزء الذي يستبدله HTMX، فالنقرُ مفوَّضٌ على document وحالةُ aria-pressed تُعاد بعد كلّ استبدال.
 */
(function () {
  "use strict";
  var KEY = "movementView";
  var root = document.documentElement;

  function saved() {
    try {
      var v = window.localStorage.getItem(KEY);
      return v === "table" || v === "cards" ? v : null;
    } catch (e) { return null; }
  }

  function effective() {
    return root.getAttribute("data-movement-view") ||
      (window.matchMedia("(max-width: 768px)").matches ? "cards" : "table");
  }

  function sync() {
    var current = effective();
    document.querySelectorAll("[data-movement-view-btn]").forEach(function (b) {
      b.setAttribute("aria-pressed", b.getAttribute("data-movement-view-btn") === current ? "true" : "false");
    });
  }

  var initial = saved();
  if (initial) root.setAttribute("data-movement-view", initial);

  document.addEventListener("click", function (ev) {
    var btn = ev.target.closest && ev.target.closest("[data-movement-view-btn]");
    if (!btn) return;
    var view = btn.getAttribute("data-movement-view-btn");
    root.setAttribute("data-movement-view", view);
    try { window.localStorage.setItem(KEY, view); } catch (e) { /* لا تخزين */ }
    sync();
  });
  document.addEventListener("htmx:afterSettle", sync);
  document.addEventListener("DOMContentLoaded", sync);
})();

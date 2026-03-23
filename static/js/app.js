/* SchoolOS — app.js v5.2 */
'use strict';
(function () {

  /* ── Swipe يساراً على إشعار → تحديد كمقروء ──────────────── */
  function initSwipe(el) {
    var sx = 0;
    el.addEventListener('touchstart', function (e) {
      sx = e.touches[0].clientX;
    }, { passive: true });
    el.addEventListener('touchend', function (e) {
      var dx = e.changedTouches[0].clientX - sx;
      if (dx < -60) {
        var btn = el.querySelector('button[hx-post]');
        if (btn) btn.click();
      }
    }, { passive: true });
  }

  function initAllSwipes() {
    document.querySelectorAll('.notif-item').forEach(initSwipe);
  }

  document.addEventListener('DOMContentLoaded', initAllSwipes);
  document.addEventListener('htmx:afterSwap', initAllSwipes);

})();

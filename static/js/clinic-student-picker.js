/* مكوّن اختيار الطالب في العيادة (W-20261102-001) — لوحة مفاتيح + ملءُ حقل النموذج.
   ↓/↑: التنقّل بين النتائج، Enter: اختيار، Esc: رجوعٌ إلى الحقل، وفي التأكيد Esc يُلغي. */
(function () {
  'use strict';

  function root() { return document.querySelector('[data-student-picker]'); }
  function buttons() { return Array.prototype.slice.call(document.querySelectorAll('[data-pick-list] .clinic-pick')); }

  function pickIntoForm(btn) {
    var hidden = document.getElementById('f-student_id');
    var label = document.querySelector('[data-pick-label-field]');
    if (!hidden || !label) return;
    hidden.value = btn.getAttribute('data-pick-id');
    label.value = btn.getAttribute('data-pick-label');
    label.setCustomValidity('');
    var reason = document.getElementById('f-reason');
    if (reason) reason.focus();
  }

  document.addEventListener('click', function (e) {
    var pick = e.target.closest && e.target.closest('[data-pick-id]');
    if (pick) { pickIntoForm(pick); return; }
    var cancel = e.target.closest && e.target.closest('[data-pick-cancel]');
    if (cancel) {
      var panel = document.getElementById('quick-panel');
      if (panel) panel.innerHTML = '';
      var input = document.querySelector('[data-pick-input]');
      if (input) input.focus();
    }
  });

  document.addEventListener('keydown', function (e) {
    var r = root();
    if (!r) return;
    var list = buttons();
    var input = r.querySelector('[data-pick-input]');
    var idx = list.indexOf(document.activeElement);
    if (e.key === 'ArrowDown') {
      if (document.activeElement === input || idx >= 0) {
        e.preventDefault();
        var next = list[idx + 1] || list[0];
        if (next) next.focus();
      }
    } else if (e.key === 'ArrowUp' && idx >= 0) {
      e.preventDefault();
      if (idx === 0) { input.focus(); } else { list[idx - 1].focus(); }
    } else if (e.key === 'Escape') {
      var panel = document.getElementById('quick-panel');
      if (panel && panel.firstElementChild) { panel.innerHTML = ''; }
      if (input) input.focus();
    }
  });

  /* بعد عرض التأكيد يذهب التركيزُ إلى زرّ التأكيد فيكفي Enter. */
  document.body.addEventListener('htmx:afterSwap', function (e) {
    if (e.target && e.target.id === 'quick-panel') {
      var ok = e.target.querySelector('[data-pick-confirm]');
      if (ok) ok.focus();
    }
  });
})();

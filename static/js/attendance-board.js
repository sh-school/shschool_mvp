/**
 * لوحةُ رصد حضور الموظّفين — بحثٌ وترشيحٌ بالحالة في المتصفّح بلا طلب خادم:
 * كادرُ المدرسة كلُّه مرسومٌ في الصفحة أصلاً (بطاقتان: الأكاديميّ والإداريّ). والبحثُ عربيٌّ ذكيّ
 * (`smartMatch` من base.js: يُسقط التشكيلَ ويوحّد الهمزات وكلُّ كلمةٍ يجب أن تطابق). وبعد كلّ رصدٍ
 * يستبدل HTMX سطرَه بنسخةٍ جديدة، فيُعاد الترشيحُ: من رُصد وهو في قائمة «لم يُرصد» يغادرها.
 */
(function () {
  'use strict';
  var board = document.getElementById('att-board');
  var query = document.getElementById('board-q');
  var state = document.getElementById('board-status');
  if (!board || !query || !state) return;

  var count = document.getElementById('board-count');
  var timer = null;

  function matches(row, text, wanted) {
    if (wanted && row.getAttribute('data-state') !== wanted) return false;
    if (!text) return true;
    var info = row.querySelector('.att-row__name');
    var number = row.querySelector('.att-row__nid');
    var haystack = (info ? info.textContent : '') + ' ' + (number ? number.textContent : '');
    return window.smartMatch ? window.smartMatch(text, haystack) : haystack.indexOf(text) !== -1;
  }

  function apply() {
    var text = query.value.trim();
    var wanted = state.value;
    var shown = 0;
    var total = 0;
    board.querySelectorAll('[data-att-list]').forEach(function (list) {
      var rows = list.querySelectorAll('.att-row--staff');
      var visible = 0;
      rows.forEach(function (row) {
        var ok = matches(row, text, wanted);
        row.hidden = !ok;
        if (ok) visible++;
      });
      var empty = list.nextElementSibling;
      if (empty && empty.classList.contains('att-board__empty')) empty.hidden = visible !== 0;
      shown += visible;
      total += rows.length;
    });
    if (count) count.textContent = (text || wanted) ? shown + ' من ' + total : total + ' موظّفاً';
  }

  query.addEventListener('input', function () {
    clearTimeout(timer);
    timer = setTimeout(apply, 120);
  });
  query.addEventListener('keydown', function (event) {
    if (event.key === 'Escape') { query.value = ''; apply(); }
    // Enter في حقل بحثٍ داخل نموذج GET يعيد تحميل الصفحة؛ والبحثُ حيٌّ فلا حاجة.
    if (event.key === 'Enter') event.preventDefault();
  });
  state.addEventListener('change', apply);
  board.addEventListener('htmx:afterSwap', apply);
  apply();
})();

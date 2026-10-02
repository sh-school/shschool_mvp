/**
 * لوحةُ رصد حضور الموظّفين — بحثٌ وترشيحٌ بالحالة في المتصفّح بلا طلب خادم:
 * كادرُ المدرسة كلُّه مرسومٌ في الصفحة أصلاً. والبحثُ عربيٌّ ذكيّ (`smartMatch` من base.js:
 * يُسقط التشكيلَ ويوحّد الهمزات وكلُّ كلمةٍ يجب أن تطابق). وبعد كلّ رصدٍ يستبدل HTMX
 * سطرَه بنسخةٍ جديدة، فيُعاد الترشيحُ: من رُصد وهو في قائمة «لم يُرصد» يغادرها.
 */
(function () {
  'use strict';
  var list = document.getElementById('att-board-list');
  var query = document.getElementById('board-q');
  var state = document.getElementById('board-status');
  if (!list || !query || !state) return;

  var count = document.getElementById('board-count');
  var empty = document.getElementById('board-empty');
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
    var rows = list.querySelectorAll('.att-row--staff');
    var text = query.value.trim();
    var wanted = state.value;
    var shown = 0;
    rows.forEach(function (row) {
      var ok = matches(row, text, wanted);
      row.hidden = !ok;
      if (ok) shown++;
    });
    if (count) {
      count.textContent = (text || wanted) ? shown + ' من ' + rows.length : rows.length + ' موظّفاً';
    }
    if (empty) empty.hidden = shown !== 0;
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
  list.addEventListener('htmx:afterSwap', apply);
  apply();
})();

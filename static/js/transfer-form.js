/**
 * نموذج طلب الانتقال: عند اختيار الطالب يظهر صفّه وشعبته ويُملأ «الصف (من)»،
 * وفي الانتقال الداخلي تُعرض الشعبةُ المنقول إليها من صفّه وحدَه دون شعبته الحاليّة (W-20261005-008).
 * الخادمُ هو الحَكَم (يرفض هدفاً من صفٍّ آخر)؛ هذا تيسيرٌ لا حرّاسة. لا CSP inline: كلُّه بسمات `data-*`.
 */
(function () {
  'use strict';

  var form = document.querySelector('[data-transfer-form]');
  if (!form) return;
  var student = form.querySelector('#f-student_id');
  var hint = form.querySelector('[data-student-class]');
  var direction = form.querySelector('[name=direction]');
  var fromGrade = form.querySelector('[name=from_grade]');
  var target = form.querySelector('#f-to_class_group_id');
  var internalOnly = form.querySelectorAll('[data-internal-only]');
  var externalOnly = form.querySelectorAll('[data-external-only]');

  function current() { return student && student.options[student.selectedIndex]; }

  function sync() {
    var option = current();
    var grade = option ? option.getAttribute('data-grade') || '' : '';
    var classId = option ? option.getAttribute('data-class-id') || '' : '';
    var label = option ? option.getAttribute('data-class-label') || '' : '';
    if (hint) hint.textContent = option && option.value ? 'الصفّ والشعبة: ' + label : '';
    if (fromGrade && grade) fromGrade.value = grade;
    var internal = direction && direction.value === 'internal';
    internalOnly.forEach(function (node) { node.hidden = !internal; });
    externalOnly.forEach(function (node) { node.hidden = internal; });
    if (!target) return;
    Array.prototype.forEach.call(target.options, function (item) {
      if (!item.value) return;
      var match = internal && grade && item.getAttribute('data-grade') === grade && item.value !== classId;
      item.hidden = !match;
      item.disabled = !match;
      if (!match && item.selected) target.value = '';
    });
  }

  if (student) student.addEventListener('change', sync);
  if (direction) direction.addEventListener('change', sync);
  sync();
})();

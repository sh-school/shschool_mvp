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
  var otherSchool = form.querySelector('[name=other_school_name]');
  var internalOnly = form.querySelectorAll('[data-internal-only]');
  var externalOnly = form.querySelectorAll('[data-external-only]');

  var search = form.querySelector('#f-student_q');
  var results = form.querySelector('[data-student-results]');

  // الطالبُ المختار حقلٌ مخفيّ يحمل صفَّه وشعبته في سمات data-*؛ يُمسح إن عاد المستخدم يكتب فيُعاد الاختيار.
  function current() { return student; }

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
    // الحقلُ المخفيّ المُعلَّم required يمنع المتصفّحَ من الإرسال دون أن يُظهر رسالةً عليه (W-20261106-020):
    // فيُرفع عنه required حين يُخفى، ويُشترط اختيارُ الشعبة حين تظهر في الداخليّ وحدَه.
    if (otherSchool) otherSchool.required = !internal;
    if (target) target.required = internal;
    if (!target) return;
    Array.prototype.forEach.call(target.options, function (item) {
      if (!item.value) return;
      var match = internal && grade && item.getAttribute('data-grade') === grade && item.value !== classId;
      item.hidden = !match;
      item.disabled = !match;
      if (!match && item.selected) target.value = '';
    });
  }

  if (results) {
    results.addEventListener('click', function (event) {
      var pick = event.target.closest('[data-student-pick]');
      if (!pick || !student) return;
      student.value = pick.getAttribute('data-id');
      ['data-grade', 'data-class-id', 'data-class-label'].forEach(function (name) {
        student.setAttribute(name, pick.getAttribute(name) || '');
      });
      if (search) search.value = pick.getAttribute('data-name') || '';
      results.textContent = '';
      sync();
    });
  }
  if (search && student) {
    search.addEventListener('input', function () {
      student.value = '';
      ['data-grade', 'data-class-id', 'data-class-label'].forEach(function (name) {
        student.setAttribute(name, '');
      });
      sync();
    });
  }
  if (student) student.addEventListener('change', sync);
  if (direction) direction.addEventListener('change', sync);
  sync();
})();

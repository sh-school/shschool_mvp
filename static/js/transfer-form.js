/**
 * نموذج طلب الانتقال: بحثُ الطالب بنمط ARIA 1.2 combobox مع listbox،
 * وعند اختياره يظهر صفّه وشعبته، وفي الانتقال الداخلي تُعرض الشعبةُ المنقول إليها
 * من صفّه وحدَه دون شعبته الحاليّة (W-20261005-008، W-20261123-013).
 * الخادمُ هو الحَكَم (يرفض هدفاً من صفٍّ آخر وطلباً بلا طالب)؛ هذا تيسيرٌ لا حرّاسة.
 * لا CSP inline: كلُّه بسمات `data-*`.
 */
(function () {
  'use strict';

  var form = document.querySelector('[data-transfer-form]');
  if (!form) return;
  var student = form.querySelector('#f-student_id');
  var direction = form.querySelector('[name=direction]');
  var target = form.querySelector('#f-to_class_group_id');
  var otherSchool = form.querySelector('[name=other_school_name]');
  var internalOnly = form.querySelectorAll('[data-internal-only]');
  var externalOnly = form.querySelectorAll('[data-external-only]');
  var reason = form.querySelector('[name=reason]');
  var counter = form.querySelector('[data-reason-count]');
  var summary = form.querySelector('[data-transfer-summary]');

  var search = form.querySelector('#f-student_q');
  var list = form.querySelector('[data-student-results]');
  var card = form.querySelector('[data-student-picked]');
  var status = form.querySelector('[data-student-status]');
  var clientError = form.querySelector('[data-student-error]');
  var MIN_QUERY = 2;
  var STUDENT_ATTRS = ['data-grade', 'data-class-id', 'data-class-label'];
  var active = -1;

  function options() { return list ? list.querySelectorAll('[role=option]') : []; }
  function say(text) { if (status) status.textContent = text; }
  function query() { return search ? search.value.trim() : ''; }

  function sync() {
    var grade = student ? student.getAttribute('data-grade') || '' : '';
    var classId = student ? student.getAttribute('data-class-id') || '' : '';
    var internal = direction && direction.value === 'internal';
    internalOnly.forEach(function (node) { node.hidden = !internal; });
    externalOnly.forEach(function (node) { node.hidden = internal; });
    // الحقلُ المخفيّ المُعلَّم required يمنع المتصفّحَ من الإرسال دون أن يُظهر رسالةً عليه (W-20261106-020):
    // فيُرفع عنه required حين يُخفى، ويُشترط اختيارُ الشعبة حين تظهر في الداخليّ وحدَه.
    if (otherSchool) otherSchool.required = !internal;
    if (target) target.required = internal;
    // سببُ الانتقال إلزاميّ في الصادر وحده (والخادمُ يتحقّق من ذلك).
    if (reason) reason.required = direction && direction.value === 'out';
    if (!target) return;
    Array.prototype.forEach.call(target.options, function (item) {
      if (!item.value) return;
      var match = internal && grade && item.getAttribute('data-grade') === grade && item.value !== classId;
      item.hidden = !match;
      item.disabled = !match;
      if (!match && item.selected) target.value = '';
    });
    summarize(internal, classId);
  }

  // ملخّصُ الاتجاه: «من 10/4 إلى 10/2» يتحدّث فور اختيار الطالب والشعبة في الداخليّ.
  function summarize(internal, classId) {
    if (!summary) return;
    var from = student ? student.getAttribute('data-class-label') || '' : '';
    var option = target && target.selectedIndex > 0 ? target.options[target.selectedIndex] : null;
    var ready = internal && classId && from && option && option.value;
    summary.hidden = !ready;
    summary.textContent = ready ? 'من ' + from + ' إلى ' + option.textContent.trim() : '';
  }

  // عدّادُ أحرف السبب.
  function countReason() {
    if (reason && counter) counter.textContent = reason.value.length + ' / ' + (reason.maxLength > 0 ? reason.maxLength : 1000);
  }

  // اللوحةُ: فتحُها وإغلاقُها وتحريكُ الصفّ النشط (aria-activedescendant).
  function setActive(index) {
    var items = options();
    active = items.length ? (index + items.length) % items.length : -1;
    Array.prototype.forEach.call(items, function (item, i) {
      item.setAttribute('aria-selected', i === active ? 'true' : 'false');
    });
    if (active >= 0) {
      search.setAttribute('aria-activedescendant', items[active].id);
      items[active].scrollIntoView({ block: 'nearest' });
    } else {
      search.removeAttribute('aria-activedescendant');
    }
  }

  function setOpen(open) {
    if (!list || !search) return;
    list.hidden = !open;
    search.setAttribute('aria-expanded', open ? 'true' : 'false');
    if (!open) setActive(-1);
  }

  // إبرازُ الجزء المطابق لما كُتب بعُقد DOM (لا innerHTML فلا حقنَ).
  function highlight() {
    var q = query().toLowerCase();
    Array.prototype.forEach.call(list.querySelectorAll('[data-option-name]'), function (node) {
      var text = node.textContent;
      var at = q ? text.toLowerCase().indexOf(q) : -1;
      if (at < 0) return;
      var mark = document.createElement('mark');
      mark.className = 'sa-combo__mark';
      mark.textContent = text.slice(at, at + q.length);
      node.textContent = '';
      node.appendChild(document.createTextNode(text.slice(0, at)));
      node.appendChild(mark);
      node.appendChild(document.createTextNode(text.slice(at + q.length)));
    });
  }

  function showResults() {
    var count = options().length;
    if (query().length < MIN_QUERY) {
      list.textContent = '';
      setOpen(false);
      say('اكتب حرفين على الأقل من اسم الطالب.');
      return;
    }
    list.removeAttribute('aria-busy');
    if (!count) {
      setOpen(false);
      say('لا طالب بهذا الاسم.');
      return;
    }
    highlight();
    setOpen(true);
    setActive(-1);
    say('تمّ العثور على ' + count + ' من الطلبة. استعمل الأسهم للتنقّل ثم Enter للاختيار.');
  }

  function showPicked(name, classLabel) {
    card.querySelector('[data-picked-name]').textContent = name;
    card.querySelector('[data-picked-class]').textContent = classLabel;
    card.hidden = false;
    search.hidden = true;
    search.value = '';
  }

  function pick(item) {
    if (!item || !student) return;
    student.value = item.getAttribute('data-id');
    STUDENT_ATTRS.forEach(function (name) { student.setAttribute(name, item.getAttribute(name) || ''); });
    showPicked(item.getAttribute('data-name') || '', item.getAttribute('data-class-label') || '');
    list.textContent = '';
    setOpen(false);
    if (clientError) clientError.hidden = true;
    sync();
    say('اخترتَ الطالب ' + (item.getAttribute('data-name') || '') + '.');
    // الانتقالُ الداخليّ: ينتقل التركيزُ إلى قائمة الشعبة المنقول إليها.
    var next = direction && direction.value === 'internal' && target ? target : card.querySelector('[data-student-clear]');
    next.focus();
  }

  function clearPick() {
    if (!student) return;
    student.value = '';
    STUDENT_ATTRS.forEach(function (name) { student.setAttribute(name, ''); });
    card.hidden = true;
    search.hidden = false;
    search.value = '';
    sync();
    say('اكتب حرفين على الأقل من اسم الطالب.');
    search.focus();
  }

  if (list && search && student && card) {
    list.addEventListener('mousedown', function (event) { event.preventDefault(); });
    list.addEventListener('click', function (event) { pick(event.target.closest('[data-student-pick]')); });
    card.querySelector('[data-student-clear]').addEventListener('click', clearPick);

    search.addEventListener('input', function () {
      if (query().length < MIN_QUERY) showResults();
    });
    search.addEventListener('keydown', function (event) {
      var items = options();
      var open = !list.hidden && items.length > 0;
      if (event.key === 'Escape') {
        if (open) event.preventDefault();
        setOpen(false);
      } else if (event.key === 'Tab') {
        setOpen(false); // يُغلق دون اختيار
      } else if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
        event.preventDefault();
        if (!open) return;
        setActive(active < 0 ? (event.key === 'ArrowDown' ? 0 : -1) : active + (event.key === 'ArrowDown' ? 1 : -1));
      } else if (open && event.key === 'Home') {
        event.preventDefault();
        setActive(0);
      } else if (open && event.key === 'End') {
        event.preventDefault();
        setActive(items.length - 1);
      } else if (event.key === 'Enter' && open && active >= 0) {
        event.preventDefault();
        pick(items[active]);
      }
    });
    search.addEventListener('blur', function () { setOpen(false); });
    search.addEventListener('focus', function () {
      if (query().length < MIN_QUERY) say('اكتب حرفين على الأقل من اسم الطالب.');
    });

    // حالةُ «جارٍ البحث» وعددُ النتائج من أحداث HTMX.
    form.addEventListener('htmx:beforeRequest', function (event) {
      if (event.target !== search) return;
      if (query().length >= MIN_QUERY) {
        list.setAttribute('aria-busy', 'true');
        say('جارٍ البحث…');
      }
    });
    form.addEventListener('htmx:afterSwap', function (event) { if (event.target === list) showResults(); });
    form.addEventListener('htmx:responseError', function (event) {
      if (event.target !== list && event.target !== search) return;
      list.removeAttribute('aria-busy');
      say('تعذّر البحث، حاول مرّةً أخرى.');
    });
    form.addEventListener('htmx:sendError', function () {
      list.removeAttribute('aria-busy');
      say('تعذّر البحث، حاول مرّةً أخرى.');
    });

    // منعُ الإرسال دون اختيار: رسالةٌ عربيّةٌ صريحة بدل رسالة المتصفّح، وتُفحص قبل تحقّق المتصفّح.
    var submit = form.querySelector('[type=submit]');
    if (submit) {
      submit.addEventListener('click', function (event) {
        if (student.value) return;
        event.preventDefault();
        if (clientError) clientError.hidden = false;
        search.setAttribute('aria-invalid', 'true');
        search.focus();
      });
    }
    search.addEventListener('input', function () {
      search.removeAttribute('aria-invalid');
      if (clientError) clientError.hidden = true;
    });
  }
  if (direction) direction.addEventListener('change', sync);
  if (target) target.addEventListener('change', sync);
  if (reason) reason.addEventListener('input', countReason);
  countReason();
  sync();
})();

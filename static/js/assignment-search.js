/**
 * شاشةُ الإسناد — بحثٌ حيٌّ باسم المعلّم: تصفيةٌ فوريّةٌ في المتصفّح بلا
 * طلب خادم، فكلُّ البطاقات مرسومةٌ في الصفحة أصلاً. القسمُ الذي لا يطابقه
 * أحدٌ يُخفى، والذي يطابقه يُفتح تلقائيّاً — فلا نقرةَ إضافيّةً بعد الكتابة.
 */
(function () {
  'use strict';
  var input = document.getElementById('asg-teacher-search');
  if (!input) return;

  var timer = null;

  function apply(raw) {
    var query = raw.trim().toLowerCase();
    document.querySelectorAll('.asg-dept-fold').forEach(function (dept) {
      var matches = 0;
      dept.querySelectorAll('.asg-card').forEach(function (card) {
        var name = card.querySelector('.asg-name');
        var hit = !query || (name && name.textContent.toLowerCase().indexOf(query) !== -1);
        card.hidden = !hit;
        if (hit) matches++;
      });
      dept.hidden = !!query && matches === 0;
      if (query && matches > 0) dept.open = true;
    });
  }

  input.addEventListener('input', function () {
    clearTimeout(timer);
    var value = input.value;
    timer = setTimeout(function () { apply(value); }, 160);
  });
  input.addEventListener('keydown', function (event) {
    if (event.key === 'Escape') { input.value = ''; apply(''); }
  });
})();

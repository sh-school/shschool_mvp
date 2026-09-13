/**
 * شاشةُ الإسناد — «فتحُ الكلّ» و«طيُّ الكلّ» لبطاقات المعلّمين المطويّة.
 */
(function () {
  'use strict';
  document.addEventListener('click', function (event) {
    var button = event.target.closest('[data-asg-fold]');
    if (!button) return;
    var open = button.getAttribute('data-asg-fold') === 'open';
    document.querySelectorAll('details.asg-fold').forEach(function (fold) { fold.open = open; });
  });
})();

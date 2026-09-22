/**
 * شاشةُ الإسناد — مفتاحان يبدّل كلٌّ منهما حالته بنفسه (فتحٌ فطيٌّ فتحٌ...):
 * «فتحُ/طيُّ الأقسام» لعناوين الأقسام وحدَها، و«فتحُ/طيُّ الكلّ» لها وللبطاقات معاً.
 */
(function () {
  'use strict';
  var LABELS = {
    dept: ['فتحُ الأقسام', 'طيُّ الأقسام'],
    all: ['فتحُ الكلّ', 'طيُّ الكلّ'],
  };
  var SELECTORS = {
    dept: 'details.asg-dept-fold',
    all: 'details.asg-fold, details.asg-dept-fold',
  };

  document.addEventListener('click', function (event) {
    var button = event.target.closest('[data-asg-fold-toggle]');
    if (!button) return;
    var scope = button.getAttribute('data-asg-fold-toggle');
    var open = button.getAttribute('data-open') !== 'true';
    button.setAttribute('data-open', String(open));
    button.setAttribute('aria-pressed', String(open));
    button.textContent = LABELS[scope][open ? 1 : 0];
    document.querySelectorAll(SELECTORS[scope]).forEach(function (fold) { fold.open = open; });
  });
})();

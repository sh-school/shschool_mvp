/* استمارة الزيارة الصفّية — قائمةُ «إدراج مؤشّر» بجوار خانة التوصية (بلاغ 7640).
 *
 * عناصرُ القائمة تحمل نصوصَ المؤشّرات من INDICATORS حرفيّاً (مصدرٌ واحد في الكود)، فلا نسخَ هنا.
 * الاختيارُ يضيف النصَّ إلى نهاية التوصية في سطر جديد دون مسح ما كُتب، ثم تعود القائمةُ للعنوان
 * ليمكن اختيارُ مؤشّرٍ آخر بالتتابع. الخانةُ تبقى قابلةً للتحرير.
 *
 * تفويضٌ من `document` بـ`change` لا `onclick` في القالب (CSP nonce)، فيعمل بعد كل إعادة رسم.
 */
(function () {
  'use strict';

  document.addEventListener('change', function (event) {
    var select = event.target;
    if (!select.matches || !select.matches('select[data-action="insert-indicator"]')) return;

    var text = select.value;
    select.selectedIndex = 0;
    if (!text) return;

    var area = select.closest('td').querySelector('textarea');
    if (!area) return;

    // سطرٌ جديد قبل النصّ إلّا إن كانت الخانةُ فارغةً أو تنتهي بسطرٍ جديد أصلاً
    var separator = area.value && !/\n$/.test(area.value) ? '\n' : '';
    area.value += separator + text;
    area.dispatchEvent(new Event('input', { bubbles: true }));
  });
})();

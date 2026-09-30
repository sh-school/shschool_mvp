/* شجرةُ عارض الوثائق: تبديلُ الصفحة (page-nav.js) يستبدل main-content كاملاً،
   فيولد عمودُ الشجرة من جديدٍ بتمريرٍ صفريّ — يبدو كأنّها «تعود إلى الأعلى» مع
   كلّ اختيار ملفٍّ (ملاحظةُ المالك). هذا يُبقي الملفَّ الحاليَّ ظاهراً بعد كلّ
   تبديلٍ بلا قفزةٍ إن كان ظاهراً أصلاً (`block: 'nearest'` لا `'center'`). */
(function () {
  document.addEventListener('htmx:afterSwap', function () {
    var current = document.querySelector('.docs-tree__file.is-current');
    if (current) current.scrollIntoView({ block: 'nearest' });
  });
})();

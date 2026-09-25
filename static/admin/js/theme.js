'use strict';
/* الإدارةُ نهاريّةٌ افتراضيّاً للجميع كالمنصّة (قرارُ المالك 2026-09-25) — تحلّ محلَّ admin/js/theme.js في جانغو.

   كان الأصلُ ثلاثيَّ الحالات (auto وlight وdark): يقرأ `prefers-color-scheme` حين لا اختيار، فتُفتح الإدارةُ ليليّةً
   على جهازٍ ليليّ والمنصّةُ نهاريّةٌ (لا تقرأ النظام). وهنا حالتان فقط، والمفتاحُ `localStorage['theme']` هو الذي
   تكتبه المنصّةُ نفسُها (`dark` أو `light`):

   - `dark` وحدَه يفتح الليليَّ؛ وكلُّ ما سواه (لا قيمة، أو `auto` قديمة من الأصل، أو أيّ شيء) نهاريّ.
   - لا يُكتب المفتاحُ عند الفتح — يُكتب حين يضغط المستخدمُ زرَّ الوضع فقط، كالمنصّة.
   - `data-theme` لا يكون `auto` أبداً، فلا تغلب قواعدُ dark_mode.css المشروطةُ بالنظام قواعدَ الوضع الصريح. */
{
    function stored() {
        try {
            return localStorage.getItem('theme');
        } catch (e) {
            return null; // لا تخزين (وضعٌ خاصّ) — نهاريّ
        }
    }

    function apply(mode) {
        document.documentElement.dataset.theme = mode === 'dark' ? 'dark' : 'light';
    }

    function toggle() {
        var next = document.documentElement.dataset.theme === 'dark' ? 'light' : 'dark';
        apply(next);
        try {
            localStorage.setItem('theme', next);
        } catch (e) { /* لا تخزين: يبقى الاختيارُ لهذه الصفحة */ }
    }

    window.addEventListener('load', function () {
        Array.prototype.forEach.call(document.getElementsByClassName('theme-toggle'), function (btn) {
            btn.addEventListener('click', toggle);
        });
    });

    apply(stored()); // متزامنٌ في الرأس — قبل أوّل رسمٍ فلا وميض
}

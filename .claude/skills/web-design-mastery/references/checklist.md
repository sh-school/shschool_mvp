# Checklist الكامل — 10 كتب تصميم ويب

راجع هذه القائمة قبل كل تعديل على HTML/CSS/Templates.

---

## 1. البنية (Resilient Web Design + Adaptive Web Design)
- [ ] HTML يعمل بدون CSS وبدون JS؟
- [ ] كل form فيه `action` + `method` يعمل بدون JS؟
- [ ] Feature detection بدل browser detection؟
- [ ] `@supports` للـ CSS الحديث مع fallback؟
- [ ] كل صفحة تُتنقل بـ `<a href>` عادية؟
- [ ] Semantic HTML: `<nav>`, `<main>`, `<article>`, `<header>`, `<footer>`؟
- [ ] العناوين بترتيب h1 > h2 > h3 بدون قفز؟
- [ ] `<button>` للأفعال، `<a>` للتنقل — لا `<div onclick>`؟

## 2. الأداء (Designing for Performance)
- [ ] الصور بـ WebP + fallback؟
- [ ] `loading="lazy"` للصور تحت الطي؟
- [ ] `width` + `height` على كل `<img>` (يمنع CLS)؟
- [ ] `fetchpriority="high"` لصورة LCP؟
- [ ] الخطوط: WOFF2 + `font-display: swap/optional`؟
- [ ] Preload للخط الأساسي؟
- [ ] CSS/JS مضغوط ومصغّر؟
- [ ] لا `@import` في CSS — `<link>` فقط؟
- [ ] LCP < 2.5s, INP < 200ms, CLS < 0.1؟
- [ ] Performance Budget محترم؟ (Dashboard < 800KB, جوال < 500KB)

## 3. التصميم المرئي (Designing for the Web + Trends)
- [ ] 3 ألوان غير رمادية كحد أقصى؟
- [ ] هيكل اللوحة: Base + Dominant + Accent؟
- [ ] PARC: قرب + محاذاة + تكرار + تباين؟
- [ ] تسلسل بصري واضح (حجم + لون + موضع)؟
- [ ] whitespace كافي في الجداول والبطاقات؟
- [ ] Flat 2.0 + ظلال خفيفة للـ affordance؟
- [ ] Cards للتصفح، Lists للمقارنة؟
- [ ] Micro-interactions تعطي feedback فوري؟
- [ ] لا تأثيرات ثقيلة تؤثر على الأداء؟

## 4. CSS (The Magic of CSS)
- [ ] `border-box` مفعّل عالمياً؟
- [ ] لا `#id` في selectors — `.class` فقط؟
- [ ] Grid للتخطيط الكلي + Flexbox للمكونات؟
- [ ] أنيميشن: `transform` + `opacity` فقط؟
- [ ] `prefers-reduced-motion` محترم؟
- [ ] لا `!important` جديدة؟
- [ ] لا inline styles جديدة — CSS class بدلاً؟
- [ ] لا `<style>` blocks في templates؟
- [ ] كل CSS في الملف المركزي؟
- [ ] رفعت `?v=N` بعد تعديل CSS؟

## 5. التجاوب (Responsive & Adaptive Web Design)
- [ ] Mobile-first: `min-width` queries؟
- [ ] Breakpoints من المحتوى لا من الأجهزة؟
- [ ] Touch targets ≥ 44×44px؟
- [ ] لا `user-scalable=no`؟
- [ ] لا `maximum-scale=1`؟
- [ ] Typography متجاوب: `clamp()`؟
- [ ] Container queries للمكونات المستقلة؟
- [ ] الجداول: card layout على الجوال أو scroll أفقي؟

## 6. الطباعة (Elements of Typographic Style)
- [ ] طول السطر 45-75 حرف (`max-width: 33em`)؟
- [ ] `line-height` بلا وحدة (1.5 لاتيني، 1.8 عربي)؟
- [ ] سلّم خطوط متناسق (CSS variables)؟
- [ ] Vertical rhythm: مسافات مضاعفات baseline؟
- [ ] UPPERCASE فيه `letter-spacing: 0.05em`؟
- [ ] لا `letter-spacing` على النص العربي أبداً؟
- [ ] `font-weight: 400` كحد أدنى للعربي؟
- [ ] لا `text-justify: inter-character` للعربي؟

## 7. الوصولية (Just Ask)
- [ ] كل input فيه `<label>` مرئي + `for`/`id`؟
- [ ] التباين ≥ 4.5:1 (نص) و ≥ 3:1 (UI)؟
- [ ] كل عنصر تفاعلي يوصَل بالكيبورد؟
- [ ] Focus ring مرئي بتباين 3:1؟
- [ ] Skip link موجود؟
- [ ] `aria-live` لرسائل الحالة الديناميكية؟
- [ ] أخطاء النماذج: inline + `aria-describedby` + `aria-invalid`؟
- [ ] `<fieldset>` + `<legend>` للحقول المرتبطة؟
- [ ] `required` + `aria-required="true"` للمطلوب؟
- [ ] كل `<img>` فيها `alt`؟
- [ ] `font-size` ≥ 12px (لا شيء أقل)؟

## 8. SVG (Pocket Guide)
- [ ] كل SVG فيه `viewBox`؟
- [ ] الأيقونات: SVG sprite + `<use>`؟
- [ ] `aria-hidden="true"` على أيقونات الزينة؟
- [ ] SVGs محسّنة بـ SVGO؟
- [ ] `focusable="false"` على SVGs داخل الأزرار؟

## 9. RTL العربي
- [ ] `<html lang="ar" dir="rtl">`؟
- [ ] CSS Logical Properties (`margin-inline-start` بدل `margin-left`)؟
- [ ] خط عربي أكبر 10-15% من اللاتيني؟
- [ ] `line-height: 1.8` للمحتوى العربي؟
- [ ] `letter-spacing: 0` على كل النص العربي؟
- [ ] Navigation تفتح من اليمين على الجوال؟
- [ ] أسهم الاتجاه معكوسة (← بدل →)؟
- [ ] `<span dir="ltr">` للنص الإنجليزي داخل العربي؟
- [ ] `hyphens: none` للعربي؟

## 10. Django تحديداً
- [ ] Logic في Service لا في View؟
- [ ] `reverse()` لا hardcoded URL؟
- [ ] لا تكرار في queryset — helper مشترك؟
- [ ] View محمية بـ `@login_required`؟
- [ ] لا `<script>` inline — كل JS في `static/js/`؟

## 11. تقارير PDF
- [ ] هوامش 20mm + هامش تجليد إضافي (RTL: يمين)؟
- [ ] خط عربي 12pt+ مع `line-height: 1.6-1.8`؟
- [ ] هيدر يتكرر كل صفحة (شعار + عنوان + رقم صفحة)؟
- [ ] فوتر يتكرر (تاريخ + سرية + صفحة X من Y)؟
- [ ] `thead { display: table-header-group; }` لتكرار هيدر الجدول؟
- [ ] Zebra striping محفوظ بـ `print-color-adjust: exact`؟
- [ ] Font embedded + subsetted (< 200KB للتقرير البسيط)؟
- [ ] Metadata: عنوان + مؤلف + تاريخ؟

## 12. ملفات Excel
- [ ] RTL: `rightToLeft=True` + `readingOrder=2`؟
- [ ] Freeze panes على الهيدر؟
- [ ] Auto-filter مفعّل؟
- [ ] تنسيق أرقام صحيح (نسب، تواريخ، أعداد)؟
- [ ] Zebra rows للقراءة؟
- [ ] `print_title_rows` لتكرار الهيدر عند الطباعة؟
- [ ] Paper size + orientation + fitToWidth؟
- [ ] Data validation على الحقول الرقمية؟

## 13. طباعة CSS (@media print)
- [ ] `@page { size: A4/A3; margin: 20mm; }`؟
- [ ] `orphans: 3; widows: 3`؟
- [ ] العناوين: `break-after: avoid`؟
- [ ] الصفوف: `break-inside: avoid`؟
- [ ] عناصر غير مطبوعة مخفية (nav, buttons, pagination)؟
- [ ] `print-color-adjust: exact` على ألوان الهيدر والحالات؟
- [ ] `thead { display: table-header-group; }`؟

## 14. التقارير المدرسية
- [ ] شعار المدرسة أعلى-يمين (RTL)؟
- [ ] مساحة ختم 30×30mm أسفل-يمين؟
- [ ] خطوط توقيع مسماة (معلم، منسق، مدير، ولي أمر)؟
- [ ] ثنائي اللغة (عربي أساسي + إنجليزي ثانوي)؟
- [ ] بيانات الطالب كاملة (اسم، رقم، صف، فصل، عام)؟
- [ ] ألوان الحالة واضحة (نجاح أخضر، رسوب أحمر)؟

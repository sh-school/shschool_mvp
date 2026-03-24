---
name: web-design-mastery
description: |
  خبير تصميم ويب احترافي (10 كتب) + معايير تقارير PDF/Excel/طباعة A4/A3. استخدم عند تعديل HTML/CSS/templates/UI، توليد PDF/Excel، تنسيق طباعة، أو بناء تقارير مدرسية. يشمل: Progressive Enhancement، Core Web Vitals، Mobile-First، CSS Grid/Flexbox/Animation، Color Theory/PARC، SVG/Icons، Typography/Type Scale/Vertical Rhythm، WCAG/ARIA/Keyboard Accessibility، Flat 2.0/Cards/Micro-interactions، RTL Arabic، ومعايير PDF وExcel وCSS @media print (A4/A3). استخدمها تلقائياً عند: إنشاء صفحة، تعديل CSS، بناء مكون UI، تحسين أداء، إصلاح تنسيق، إضافة form، صور/أيقونات/خطوط، تقارير PDF/Excel، طباعة، كشوف درجات/حضور/شهادات.
---

# Web Design Mastery — خبير تصميم ويب من 10 كتب احترافية

أنت خبير تصميم ويب تطبّق مبادئ 10 كتب احترافية في كل سطر HTML/CSS تكتبه. هذه المبادئ ليست نظرية — هي قواعد عمل يومية.

## المصادر (10 كتب)

1. **Resilient Web Design** — Jeremy Keith (Progressive Enhancement)
2. **Designing for Performance** — Lara Hogan (الأداء + Core Web Vitals)
3. **Adaptive Web Design** — Aaron Gustafson (Mobile-First + Semantic HTML)
4. **The Magic of CSS** — Adam Schwartz (Grid/Flexbox/Animation/Specificity)
5. **Designing for the Web** — Mark Boulton (Color Theory + Grid Systems + PARC)
6. **Pocket Guide to Writing SVG** — Joni Trythall (SVG + Icons + Animation)
7. **Responsive & Adaptive Web Design** — UXPin (Breakpoints + Navigation)
8. **Web Design Book of Trends** — FabricEleven (Flat 2.0 + Cards + Micro-interactions)
9. **Just Ask** — Shawn Henry (WCAG + Accessibility)
10. **Elements of Typographic Style Applied to the Web** (Typography + Rhythm)

---

## القواعد الذهبية — طبّقها في كل تعديل

### 1. Progressive Enhancement (الطبقات الثلاث)
HTML أولاً (يعمل وحده) → CSS ثانياً (العرض) → JS ثالثاً (تحسين فقط).

كل form يعمل بـ POST عادي بدون JS. كل صفحة تُتنقل بـ `<a href>` عادية. JS ليس أساساً — هو طبقة تحسين. إذا عطّلت JS يبقى الموقع يعمل.

**لماذا:** HTML/CSS يتسامحان مع المجهول (يتجاهلان ما لا يعرفانه)، لكن JS ينهار عند أي خطأ. لذلك JS لا يكون أساساً أبداً.

**أنماط عملية:**
- Ajax Hijacking: form يعمل عادي، JS يعترضه كتحسين
- `@supports (display: grid) { ... }` مع fallback flexbox
- `<script type="module">` للحديث + `<script nomodule>` للقديم

### 2. الأداء = تصميم
كل قرار تصميمي هو قرار أداء. الصور والخطوط والأنيميشن كلها تكلفة.

**Performance Budget:**
| نوع الصفحة | الحجم | الزمن |
|-------------|-------|-------|
| Dashboard | < 800KB | < 2s |
| جداول/تقارير | < 1.2MB | < 3s |
| جوال | < 500KB | < 3s (3G) |

**Core Web Vitals (2025):**
| المقياس | الهدف |
|---------|-------|
| LCP | ≤ 2.5s |
| INP | ≤ 200ms |
| CLS | ≤ 0.1 |

**الصور:** WebP + fallback، `loading="lazy"`، `width`+`height` دائماً، `fetchpriority="high"` لـ LCP.

**الخطوط:** WOFF2 فقط، `font-display: swap`، preload الأساسي. العربي: subset من 900KB إلى 100KB.

**CSS/JS:** ملف واحد مضغوط، `defer`/`async` للـ JS، Brotli compression، cache طويل + cache-busting.

### 3. Semantic HTML
استخدم العناصر لمعناها لا لشكلها:
- `<button>` للأفعال، `<a>` للتنقل — لا `<div onclick>` أبداً
- `<nav>`, `<main>`, `<article>`, `<aside>`, `<header>`, `<footer>` — لا `<div>` لكل شيء
- العناوين تصنع هيكلاً: h1 > h2 > h3 بدون قفز
- `<time datetime="...">` للتواريخ
- `<table>` للبيانات الجدولية فقط — لا للتخطيط

### 4. Mobile-First + التجاوب
صمّم للأصغر أولاً — يجبرك على ترتيب الأولويات.

- `min-width` queries لا `max-width`
- Breakpoints من المحتوى — أين ينكسر التصميم؟ تلك نقطة التوقف
- Touch targets ≥ 44×44px
- لا `user-scalable=no` أبداً
- Typography متجاوب: `font-size: clamp(1rem, 2.5vw, 1.5rem)`
- Container Queries للمكونات: `@container (min-width: 400px) { ... }`

### 5. هندسة CSS

**Box Model:** `border-box` عالمياً دائماً:
```css
html { box-sizing: border-box; }
*, *::before, *::after { box-sizing: inherit; }
```

**Layout:** Grid للتخطيط الكلي (2D)، Flexbox للمكونات الداخلية (1D).

**Specificity:** ابدأ بأخف selector. لا `#id` في CSS. لا deep nesting.

**الأنيميشن:** حرّك `transform` + `opacity` فقط (GPU-accelerated). احترم `prefers-reduced-motion`.

**ممنوعات:** لا `!important` جديدة. لا inline styles. لا `<style>` blocks في templates. كل شيء في ملف CSS المركزي.

### 6. نظام الألوان + التصميم المرئي

**3 ألوان غير رمادية كحد أقصى.** هيكل اللوحة:
- Base: لون ضعيف — الخلفيات
- Dominant: لون البراند — الهوية
- Accent: لون قوي — الأزرار والتنبيهات

**PARC (مبادئ التصميم الأربعة):**
- **Proximity:** عناصر مرتبطة = قريبة
- **Alignment:** كل عنصر له اتصال بصري بآخر
- **Repetition:** كرّر الألوان والأشكال للتماسك
- **Contrast:** الفرق يجذب الانتباه ويصنع التسلسل

**Visual Hierarchy:** الحجم → اللون → الموضع → المسافات. في RTL: أعلى-يمين يُقرأ أولاً.

### 7. SVG والأيقونات

كل SVG فيه `viewBox`. الأيقونات: SVG sprite + `<use>`.

**وصولية SVG:**
- أيقونة + نص مرئي → `aria-hidden="true"` على SVG
- أيقونة وحدها في زر → `aria-label` على الزر
- أيقونة مستقلة ذات معنى → `role="img"` + `<title>`

تحسين: SVGO/SVGOMG (توفير 30-70%). أنيميشن: CSS transitions فقط + `prefers-reduced-motion`.

### 8. الطباعة (Typography)

**طول السطر:** 45-75 حرف (`max-width: 33em`).

**line-height بلا وحدة:** 1.5 لاتيني، 1.8 عربي.

**سلّم خطوط (Perfect Fourth 1.333 — مناسب لمنصة تعليمية):**
```css
:root {
  --scale: 1.333;
  --font-base: 1rem;
  --font-lg: calc(1rem * var(--scale));
  --font-xl: calc(1rem * var(--scale) * var(--scale));
  --font-2xl: calc(1rem * var(--scale) * var(--scale) * var(--scale));
}
```

**Vertical Rhythm:** كل المسافات العمودية مضاعفات الـ baseline (`--baseline: 1.5rem`).

**UPPERCASE:** `letter-spacing: 0.05em` إلى `0.1em`.

### 9. الوصولية (Accessibility)

**التباين:** ≥ 4.5:1 نص عادي، ≥ 3:1 نص كبير و UI.

**لوحة المفاتيح:** Tab يصل لكل عنصر تفاعلي. لا `outline: none` بدون بديل. Skip link. Escape يغلق modals.

**ARIA:** لا تستخدمه إذا HTML الأصلي يكفي. `aria-live="polite"` لرسائل الحالة. `aria-describedby` لأخطاء النماذج.

**النماذج:** كل input يحتاج `<label>` مرئي. `<fieldset>` + `<legend>` للتجميع. أخطاء inline + `aria-invalid="true"`.

### 10. RTL العربي — قواعد خاصة

| القاعدة | السبب |
|---------|-------|
| `<html lang="ar" dir="rtl">` | الأساس |
| CSS Logical Properties | `margin-inline-start` بدل `margin-left` |
| حجم عربي أكبر 10-15% | الحروف العربية أصغر بصرياً |
| `line-height: 1.8` | التشكيل والامتدادات |
| `letter-spacing: 0` دائماً | الحروف العربية متصلة — أي spacing يكسرها |
| `font-weight: 400` كحد أدنى | الأوزان الخفيفة صعبة القراءة |
| `hyphens: none` | العربية لا تستخدم الواصلة |
| Navigation من اليمين | hamburger على اليمين، القائمة تفتح من اليمين |
| أسهم معكوسة | ← بدل → |
| `<span dir="ltr">` للإنجليزي | داخل النص العربي |

**خطوط موصى بها:** عناوين: Noto Kufi Arabic, Alexandria. قراءة: Cairo, Tajawal.

---

## 11. التقارير الاحترافية — PDF + Excel + طباعة A4/A3

### معايير PDF

**الهوامش:** 2cm من كل جانب. هامش التجليد (RTL: يمين) 3cm. منطقة الطباعة الآمنة A4: 170×257mm.

**الطباعة (Typography):**
- نص عربي: 12pt كحد أدنى، `line-height: 1.6-1.8`
- عناوين: H1=20pt, H2=16pt, H3=13pt
- خطوط: Noto Sans Arabic أو IBM Plex Sans Arabic أو Cairo
- لا italic للعربي — استخدم bold أو لون بدلاً

**الجداول:**
- Header: نص أبيض bold على خلفية داكنة (لون البراند)، يتكرر كل صفحة
- Zebra striping: #F5F5F5 للصفوف الزوجية
- حدود: خطوط رمادية خفيفة (#CCC) 0.5pt أفقية
- أرقام: محاذاة وسط، `font-variant-numeric: tabular-nums`
- `thead { display: table-header-group; }` لتكرار الهيدر

**حجم الملف:** تقرير بسيط < 200KB، تقرير معقد < 1MB. Font subsetting ضروري.

### معايير Excel

**التنسيق:**
- Headers: bold أبيض على خلفية داكنة، `freeze_panes='A2'`، auto-filter
- RTL: `sheet_view.rightToLeft = True`، `readingOrder=2`
- تنسيق أرقام: `'0.0%'` للنسب، `'#,##0'` للأعداد، `'YYYY/MM/DD'` للتواريخ
- أوراق متعددة: ملخص → بيانات تفصيلية → رسوم بيانية

**إعداد الطباعة من Excel:**
- A4: `fitToWidth=1, fitToHeight=0` (كل الأعمدة في عرض صفحة واحدة)
- A3 Landscape: للجداول العريضة (حضور 31 يوم + أسماء)
- `print_title_rows='1:2'` لتكرار الهيدر

### معايير طباعة CSS (@media print)

**الأساسيات:**
```css
@page { size: A4 portrait; margin: 20mm; }
@page a3-landscape { size: A3 landscape; margin: 15mm; }
```

- `orphans: 3; widows: 3;` — لا أقل من 3 أسطر في أعلى/أسفل الصفحة
- `break-after: avoid` على العناوين — تبقى مع المحتوى التالي
- `break-inside: avoid` على البطاقات والمكونات
- `print-color-adjust: exact` للحفاظ على ألوان الخلفية
- إخفاء: nav, sidebar, buttons, pagination, search
- `thead { display: table-header-group; }` لتكرار هيدر الجدول

### أبعاد الورق

| الورق | العرض | الارتفاع | الآمن (2cm هوامش) | الاستخدام |
|-------|-------|---------|------------------|-----------|
| **A4 Portrait** | 210mm | 297mm | 170×257mm | تقارير درجات، خطابات |
| **A4 Landscape** | 297mm | 210mm | 257×170mm | شهادات، رسوم بيانية |
| **A3 Portrait** | 297mm | 420mm | 257×380mm | تقارير تفصيلية |
| **A3 Landscape** | 420mm | 297mm | 380×257mm | كشوف حضور، جداول عريضة |

### التقارير المدرسية
- **شعار المدرسة:** أعلى-يمين (RTL)، 15mm ارتفاع minimum
- **شعار الوزارة:** أعلى-يسار (اختياري حسب اللوائح)
- **مساحة الختم:** 30×30mm فارغة أسفل-يمين
- **التوقيعات:** خطوط مسماة (المعلم، المنسق، المدير، ولي الأمر)
- **ثنائي اللغة:** عربي أساسي + إنجليزي ثانوي أصغر
- **QR Code:** اختياري للتحقق الرقمي

للتفاصيل الكاملة وأمثلة الكود: اقرأ `references/reports-print.md`.

---

## Checklist — راجعه قبل كل تعديل HTML/CSS

اقرأ `references/checklist.md` للقائمة الكاملة (10 أقسام × 50+ نقطة فحص).

**الملخص السريع:**
- [ ] HTML يعمل بدون JS؟ Forms ترسل بـ POST؟
- [ ] `width`+`height` على كل `<img>`؟ `loading="lazy"`؟
- [ ] Semantic HTML؟ (`<button>` لا `<div onclick>`)
- [ ] لا `!important`، لا inline styles، لا `<style>` blocks؟
- [ ] كل input فيه `<label>` مرئي؟ التباين ≥ 4.5:1؟
- [ ] `letter-spacing: 0` على النص العربي؟
- [ ] `prefers-reduced-motion` محترم؟

---

## المراجع التفصيلية

للتعمق في أي موضوع، اقرأ الملف المناسب من `references/`:

| الملف | المحتوى |
|-------|---------|
| `references/checklist.md` | Checklist الكامل — 10 أقسام × 50+ نقطة |
| `references/performance.md` | الأداء: Performance Budget + Core Web Vitals + الصور + الخطوط |
| `references/css-architecture.md` | هندسة CSS: Grid + Flexbox + Animation + Specificity + أخطاء شائعة |
| `references/visual-design.md` | التصميم المرئي: ألوان + شبكات + PARC + اتجاهات 2025 |
| `references/accessibility.md` | الوصولية: WCAG + لوحة مفاتيح + ARIA + نماذج + اختبار |
| `references/typography.md` | الطباعة: سلّم خطوط + إيقاع عمودي + عربي |
| `references/svg-icons.md` | SVG: أساسيات + تحسين + sprites + أنيميشن + Django |
| `references/responsive.md` | التجاوب: breakpoints + تنقل + mobile-first + RTL |
| `references/patterns.md` | أنماط كود: Ajax Hijacking + Feature Detection + Django templates |
| `references/reports-print.md` | التقارير: PDF + Excel + طباعة A4/A3 + تقارير مدرسية احترافية |

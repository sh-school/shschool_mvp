---
name: web-design-mastery
description: |
  معايير التصميم والـ CSS الخاصة بمشروع SchoolOS. تحتوي: Design Tokens الفعلية من custom.css (ألوان قطرية maroon/gold، spacing، typography Tajawal)، Dark Mode الحقيقي (html.dark)، هيكل @layer الموجود، أنماط المكونات المستخدمة (nav/card/table/toast/dialog)، HTMX patterns الفعلية، معايير RTL العربي، ومعايير PDF/Excel من reports/services.py. استخدمها عند: تعديل CSS/HTML/templates، بناء مكونات، dark mode، PDF/Excel، أي عمل على الواجهة.
---

# Web Design — معايير SchoolOS الفعلية

> هذه المعايير مبنية على الكود الحقيقي في `static/css/custom.css` و `templates/base.html`.
> لا تحتوي مبادئ عامة — فقط ما هو خاص بهذا المشروع.

---

## 1. Design Tokens الحقيقية — custom.css

### الألوان (Qatar National Colors)
```css
--maroon: #8A1538;         /* اللون الرئيسي — Al Adaam */
--maroon-dark: #6b0f2a;    /* hover */
--maroon-light: #b8294e;   /* نص على خلفية فاتحة */
--maroon-bg: #fdf2f5;      /* خلفية خفيفة */
--gold: #D4A843;           /* تمييز */
--skyline: #0D4261;        /* أزرق داكن */
--palm: #129B82;           /* أخضر */
--sea: #4194B3;            /* أزرق فاتح */

--status-danger: #dc2626;
--status-warning: #d97706;
--status-success: #16a34a;
--status-info: #2563eb;

--text-primary: #111827;
--text-secondary: #4b5563;
--text-muted: #6b7280;     /* WCAG AA: 4.63:1 */
```

### Typography
```css
/* Tajawal — محلي WOFF2 + TTF (400, 500, 700) */
/* Amiri — للجداول فقط (subset ~120KB) */

--text-xs: 0.75rem;    /* 12px — labels */
--text-sm: 0.875rem;   /* 14px */
--text-base: 1rem;     /* 16px — body */
--text-lg: 1.125rem;   /* 18px */
--text-xl: 1.25rem;    /* 20px */
--text-2xl: 1.5rem;    /* 24px */
--text-3xl: 2rem;      /* 32px */
```

### Spacing + Z-index
```css
--sp-1 → --sp-16    /* 4px → 64px (multiples of 4) */
--z-base: 1, --z-dropdown: 500, --z-navbar: 1000, --z-modal: 9000, --z-toast: 9500
```

---

## 2. CSS Layers — الترتيب الفعلي

```css
@layer tailwind, reset, base, tokens, layout, components, modules, utilities;
```

**⚠️ قاعدة:** كل CSS جديد يذهب في `custom.css` داخل الـ layer المناسب. لا inline styles. لا `<style>` blocks في templates. لا `!important` جديدة.

---

## 3. Dark Mode — كيف يعمل فعلاً

```html
<!-- في <head> — script يمنع FOUC -->
<script>
  var t = localStorage.getItem('theme');
  var isDark = t==='dark' || (t!=='light' && matchMedia('(prefers-color-scheme:dark)').matches);
  if(isDark) document.documentElement.classList.add('dark');
</script>
```

**التطبيق:** `html.dark .class { ... }` في custom.css.

**⚠️ فخاخ Dark Mode:**
- خلفيات: تتحول لـ dark (مثل `#0f172a`, `#1f2937`) — **ممنوع أبيض/فاتح كخلفية**
- نصوص: تتحول لـ فاتح (`#f1f5f9`) — **أبيض/فاتح مسموح للنصوص والإطارات فقط**
- Nav: يصبح `var(--maroon-dark)` بدل `var(--maroon)`
- Cards: `background: #1f2937; color: #f1f5f9`

---

## 4. المكونات الموجودة فعلاً

### Navigation (`.site-nav`)
- Sticky top، maroon background، flex layout
- `.nb` — nav button (6px padding, white text, hover bg)
- `.nav-bell` — جرس إشعارات مع badge أحمر
- `.nav-user-btn` — avatar + dropdown
- `.nav-hamburger` — جوال فقط
- Mobile: bottom nav bar (`.mobile-bottom-nav`)

### Cards (`.card-qatar`)
- White bg، subtle shadow، border + hover
- `.card-header` مع icon slot

### Tables
- `thead` — maroon bg + white text
- `tbody tr:nth-child(even)` — alternating (surface-alt)
- `tbody tr:hover` — maroon-bg

### Flash Messages (`.msg-bar`)
- 4 أنواع: success (أخضر), error (أحمر), warning (برتقالي), info (أزرق)
- Icon + text + close button

### Dropdowns (`.sd-menu`)
- Fixed position, min-width: 210px, fade-in animation

### Progress (`.progress-qatar`)
- Gradient: maroon-dark → maroon-light

### Command Palette
- Trigger: Ctrl+K / Cmd+K
- Dialog role + combobox + listbox
- Arrow keys navigation

---

## 5. HTMX — كيف يُستخدم في المشروع

### المكتبة
- HTMX 1.9.12 محلي (`static/js/htmx.min.js`) — لا CDN
- Loading bar: `#htmx-loading-bar` (في base.html)
- SR live region: يُنبّه screen readers بتحديثات HTMX

### الأنماط المستخدمة فعلاً
```html
<!-- HTMX partial: view يرجّع partial إذا HX-Request, full page إذا لا -->
{% if request.htmx %}
  {# partial template only #}
{% else %}
  {% extends "base.html" %}
{% endif %}

<!-- Inline edit pattern (كما في assessments) -->
<td hx-get="/grades/edit/{{ grade.pk }}/"
    hx-target="this"
    hx-swap="innerHTML">{{ grade.score }}</td>

<!-- Search with debounce -->
<input hx-get="/search/"
       hx-target="#results"
       hx-trigger="input changed delay:300ms"
       hx-indicator="#spinner">
```

### Error Handling (app.js)
```javascript
// htmx:responseError → global handler
// 403 → "ليس لديك صلاحية"
// 404 → "الصفحة غير موجودة"
// 500 → "خطأ في السيرفر"
// showToast() من HX-Trigger header
```

---

## 6. RTL العربي — القواعد الثابتة

| القاعدة | الملف |
|---------|-------|
| `<html lang="ar" dir="rtl">` | base.html |
| Tajawal (400/500/700) + Amiri للجداول | custom.css @font-face |
| font-display: swap | custom.css |
| `letter-spacing: 0` للعربي | دائماً — الحروف متصلة |
| `line-height: 1.7-1.8` | custom.css |
| Nav hamburger على اليمين | base.html |
| أسهم معكوسة (← بدل →) | templates |

---

## 7. Cache Busting — الأرقام الحالية

```html
custom.css?v=124
tailwind.min.css?v=8
base.js?v=103
app.js?v=100
htmx.min.js?v=2
```

**⚠️ بعد كل تعديل CSS/JS:** ارفع الرقم في `base.html` (و `login.html` إن وجد) ثم `collectstatic`.

---

## 8. التقارير (PDF/Excel) — من reports/services.py

### Excel (ExcelService)
- **ألوان Header:** maroon `#8A1538` + white text
- **Alt rows:** `#FDF2F5` (maroon-bg)
- **RTL:** `rightToLeft = True`
- **Header:** 4 صفوف (وزارة، مدرسة، عنوان التقرير، أعمدة)
- **شعار:** badge-72.png أو icon-192.png
- **Features:** frozen headers + auto-filter + sheet protection + conditional formatting (أحمر < 50, أخضر للنجاح)
- **طباعة:** A4 portrait + repeat headers

### PDF
- WeasyPrint (django-weasyprint)
- نفس ألوان Excel
- `thead { display: table-header-group; }` لتكرار الهيدر

---

## 9. Accessibility (WCAG AA)

ما هو مُطبّق فعلاً:
- Skip navigation link (base.html)
- `aria-label` على الأزرار بدون نص
- `aria-live="polite"` لـ HTMX updates (SR live region)
- `aria-expanded` على dropdowns
- `role="dialog"` + `aria-modal` على modals
- تباين النص: `--text-muted` مُصلّح لـ 4.63:1

---

## 10. شجرة القرار — عند تعديل الواجهة

```
أين أكتب CSS؟
→ static/css/custom.css في الـ @layer المناسب — لا مكان آخر

أي لون أستخدم؟
→ var(--maroon) للبراند, var(--status-*) للحالات — لا hex مباشر

أحتاج مكون جديد؟
├── موجود؟ → استخدم الموجود (.card-qatar, .msg-bar, .data-table)
└── جديد؟ → أضفه في @layer components في custom.css

Dark mode؟
→ أضف html.dark .my-class { ... } — لا تنسَ: خلفيات داكنة + نصوص فاتحة

HTMX partial؟
→ if request.htmx → partial, else → extends base.html

بعد أي تعديل CSS/JS؟
→ 1) ارفع ?v= في base.html
→ 2) python manage.py collectstatic --noinput
→ 3) أعد تشغيل السيرفر

حجم الصفحة؟
→ Dashboard < 800KB, جداول < 1.2MB, جوال < 500KB
```

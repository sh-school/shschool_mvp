# هندسة CSS — The Magic of CSS (Adam Schwartz)

---

## Box Model — القاعدة الذهبية
```css
html { box-sizing: border-box; }
*, *::before, *::after { box-sizing: inherit; }
```
`border-box` = padding و border داخل العرض المحدد. بدونه تحدث مفاجآت في الأبعاد.

---

## Layout

| الأداة | الاستخدام | أمثلة |
|--------|-----------|-------|
| **Grid** | تخطيط 2D (صفوف + أعمدة) | Dashboard, page layout, gallery |
| **Flexbox** | تخطيط 1D (صف أو عمود) | Nav bar, card row, form group, buttons |
| **Grid + Flexbox** | Grid للصفحة، Flexbox للمكونات | الأكثر شيوعاً في التطبيقات |

**Grid أساسي:**
```css
.dashboard { display: grid; grid-template-columns: 250px 1fr; gap: 1rem; }
.cards { display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 1rem; }
```

**Flexbox أساسي:**
```css
.nav { display: flex; align-items: center; gap: 1rem; }
.card-actions { display: flex; justify-content: flex-end; gap: 0.5rem; }
```

---

## Specificity — إدارة الأولوية

**الترتيب (من الأضعف للأقوى):**
1. Element: `p`, `div` → (0,0,1)
2. Class: `.card` → (0,1,0)
3. ID: `#header` → (1,0,0)
4. Inline style → يتجاوز الكل
5. `!important` → يتجاوز كل شيء

**القواعد:**
- ابدأ بأخف selector: `.card-title` لا `div#main .container ul li a`
- لا `#id` في CSS — استخدم `.class` فقط
- لا `!important` جديدة — إذا احتجته فهناك مشكلة في الهيكل
- BEM naming: `.card__title--active`

---

## نظام الألوان

**3 ألوان غير رمادية كحد أقصى:**
- `#333` بدل `#000` للنص (أخف على العين)
- ألوان دلالية: primary, success, danger, warning, info
- `rgba(0,0,0,0.2)` بدل رمادي ثابت (يتكيف مع الخلفية)

```css
:root {
  --color-primary: #1a237e;
  --color-success: #2e7d32;
  --color-danger: #c62828;
  --color-warning: #f57f17;
  --color-text: #333;
  --color-bg: #fafafa;
}
```

---

## الأنيميشن والتحولات

**حرّك فقط `transform` + `opacity`** — GPU-accelerated، لا تسبب reflow.

```css
.card { transition: transform 0.2s ease, opacity 0.2s ease; }
.card:hover { transform: translateY(-2px); opacity: 0.95; }
```

**تأثير الموجة (staggered):**
```css
.item { transition: opacity 0.3s ease; }
.item:nth-child(1) { transition-delay: 0.05s; }
.item:nth-child(2) { transition-delay: 0.1s; }
.item:nth-child(3) { transition-delay: 0.15s; }
```

**3D:**
- `backface-visibility: hidden` لتأثير الانقلاب
- `translateZ(0)` لتفعيل GPU compositing
- `perspective` لسياق 3D

**احترام إعدادات المستخدم:**
```css
@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after {
    animation-duration: 0.01ms !important;
    transition-duration: 0.01ms !important;
  }
}
```

---

## أخطاء CSS شائعة

| الخطأ | المشكلة | الحل |
|-------|---------|------|
| `content-box` (الافتراضي) | padding/border تزيد الأبعاد | `border-box` عالمياً |
| `width/height` على `inline` | لا تأثير | `inline-block` أو `block` |
| أبعاد ثابتة بالبكسل | تنكسر عند zoom | نسب مئوية أو `rem` |
| `overflow: hidden` على `<td>` | لا يعمل بشكل موثوق | wrapper `<div>` داخل الخلية |
| `letter-spacing` على عربي | يكسر اتصال الحروف | `letter-spacing: 0` دائماً |
| Deep nesting | specificity عالية ومعقدة | BEM: `.block__element--modifier` |
| `@import` في CSS | تحميل متسلسل بطيء | `<link>` في HTML |
| `float` للتخطيط | يغيّر display value ضمنياً | Grid أو Flexbox |
| `z-index` بلا `position` | لا تأثير | أضف `position: relative` |

---

## بنية CSS في المشروع

```
custom.css — المصدر الوحيد للـ styles
├── 1. CSS Variables (--q-maroon, --q-font-ui, ...)
├── 2. Reset / Base (border-box, typography)
├── 3. Layout (page-header, sidebar, grid)
├── 4. Components (cards, badges, buttons, tables)
├── 5. Modules (quality, behavior, clinic, ...)
├── 6. Utilities (text-center, mt-1, hidden, ...)
└── 7. Responsive (@media min-width queries)
```

**قواعد ثابتة:**
- لا `<style>` blocks في أي template
- لا `!important` جديدة
- لا inline styles — CSS class في custom.css
- رفع `?v=N` عند كل تغيير

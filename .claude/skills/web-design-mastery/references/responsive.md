# التجاوب — Responsive & Adaptive Web Design (UXPin) + Adaptive (Gustafson)

---

## Workflow متجاوب

1. **جرد المحتوى** — ما البيانات في كل صفحة؟
2. **Mobile-first wireframes** — عمود واحد أولاً
3. **Breakpoints من المحتوى** — أين ينكسر التصميم؟ تلك نقطة التوقف
4. **تصميم في المتصفح** — HTML/CSS مبكراً (لا Photoshop أولاً)
5. **مكتبة مكونات** — كل مكون مسؤول عن تجاوبه
6. **اختبار على أجهزة حقيقية** — المحاكيات لا تكفي

---

## Mobile-First

**صمّم للأصغر أولاً** — يجبرك على ترتيب الأولويات.

```css
/* Base: mobile */
.container { padding: 1rem; }

/* Tablet */
@media (min-width: 48rem) {
  .container { padding: 2rem; max-width: 720px; }
}

/* Desktop */
@media (min-width: 64rem) {
  .container { max-width: 1140px; }
}
```

**قواعد:**
- `min-width` queries لا `max-width`
- Touch targets ≥ 44×44px
- لا `user-scalable=no` ولا `maximum-scale=1` أبداً
- `<meta name="viewport" content="width=device-width, initial-scale=1">`

---

## Breakpoints عملية

| النطاق | الجهاز | التخطيط |
|--------|--------|---------|
| < 480px | جوال صغير | عمود واحد، navigation مخفي |
| 481-768px | جوال كبير/تابلت صغير | عمودان لبعض المكونات |
| 769-1024px | تابلت | sidebar ظاهر + محتوى |
| 1025-1280px | سطح مكتب | تخطيط كامل |
| > 1280px | شاشة كبيرة | max-width + whitespace |

**الأفضل: `rem` بدل `px`** (يحترم إعدادات المستخدم):
```css
@media (min-width: 48rem) { /* ~768px */ }
@media (min-width: 64rem) { /* ~1024px */ }
@media (min-width: 80rem) { /* ~1280px */ }
```

**Breakpoints من المحتوى:** صغّر المتصفح حتى ينكسر التصميم → تلك نقطة التوقف. لا تعتمد على أبعاد أجهزة محددة.

---

## Container Queries (2025+)

كل مكون يستجيب لحجم حاويته لا حجم الشاشة:

```css
.card-container { container-type: inline-size; }

@container (min-width: 400px) {
  .card { flex-direction: row; }
}
@container (max-width: 399px) {
  .card { flex-direction: column; }
}
```

مفيد جداً لـ: cards, tables, sidebars داخل layouts مختلفة.

---

## أنماط التنقل المتجاوب

| النمط | الاستخدام | الإيجابيات | السلبيات |
|-------|-----------|-----------|----------|
| **Hamburger** | عام | يوفر مساحة | يخفي التنقل |
| **Priority+** | كثير من العناصر | يظهر ما يسع | معقد التنفيذ |
| **Bottom Tab Bar** | 3-5 عناصر | thumb-friendly | محدود العدد |
| **Breadcrumbs** | هرمي عميق | يوضح الموقع | مساحة أفقية |

### للـ RTL:
- Hamburger icon على **اليمين** (لا اليسار)
- القائمة تنزلق من **اليمين**
- Breadcrumbs تُقرأ من **اليمين لليسار**
- أسهم Back تشير **يميناً** (→ بدل ←)

---

## Typography متجاوب

### Fluid Typography بـ clamp()
```css
h1 { font-size: clamp(1.8rem, 4vw, 2.5rem); }
h2 { font-size: clamp(1.4rem, 3vw, 1.8rem); }
p  { font-size: clamp(1rem, 1.5vw, 1.125rem); }
```

### Responsive Type Scale
```css
/* Mobile: نسبة أضيق */
:root { --scale: 1.2; }

/* Desktop: نسبة أوسع */
@media (min-width: 48rem) {
  :root { --scale: 1.333; }
}
```

---

## الصور المتجاوبة

```html
<!-- Art direction: صورة مختلفة لكل breakpoint -->
<picture>
  <source media="(min-width: 800px)" srcset="wide.webp">
  <source media="(min-width: 400px)" srcset="medium.webp">
  <img src="small.webp" alt="وصف" width="400" height="300">
</picture>

<!-- Resolution switching: نفس الصورة بأحجام مختلفة -->
<img srcset="img-300.webp 300w, img-600.webp 600w, img-1200.webp 1200w"
     sizes="(max-width: 600px) 100vw, 50vw"
     src="img-600.webp" alt="وصف" width="600" height="400">
```

---

## الجداول المتجاوبة

### خيار 1: Scroll أفقي
```css
.table-responsive {
  overflow-x: auto;
  -webkit-overflow-scrolling: touch;
}
```

### خيار 2: Card layout على الجوال
```css
@media (max-width: 48rem) {
  table, thead, tbody, th, td, tr { display: block; }
  thead { display: none; }
  td::before {
    content: attr(data-label);
    font-weight: bold;
    display: block;
  }
}
```

---

## RTL + Responsive

### CSS Logical Properties
```css
/* ✅ يعمل مع RTL و LTR */
.card { margin-inline-start: 1rem; padding-inline-end: 0.5rem; }

/* ❌ ينكسر مع RTL */
.card { margin-left: 1rem; padding-right: 0.5rem; }
```

| Physical | Logical |
|----------|---------|
| `margin-left` | `margin-inline-start` |
| `margin-right` | `margin-inline-end` |
| `padding-left` | `padding-inline-start` |
| `text-align: left` | `text-align: start` |
| `float: left` | `float: inline-start` |
| `border-left` | `border-inline-start` |

### اختبار RTL + Responsive
- [ ] Text alignment ينعكس صحيحاً
- [ ] Navigation تفتح من اليمين
- [ ] أيقونات الاتجاه معكوسة
- [ ] الجداول تُقرأ من اليمين (scroll أفقي يبدأ من اليمين)
- [ ] الأرقام تبقى LTR داخل النص العربي
- [ ] Tab order منطقي في RTL
- [ ] النص المختلط (عربي + إنجليزي) يُعرض صحيحاً

# الطباعة — Elements of Typographic Style Applied to the Web

---

## الإيقاع الأفقي

### طول السطر (Measure)
- **45-75 حرف/سطر** مقبول
- **66 حرف** مثالي لنص القراءة
- **40-50 حرف** للأعمدة المتعددة
- استخدم `em` لعرض مرن: `max-width: 33em`

### المحاذاة
- **لا تستخدم justify** على الويب — hyphenation ضعيف
- `text-align: right` للعربية (RTL)
- `text-align: left` للإنجليزية
- Sans-serif غالباً أفضل ragged (بدون justify)

### تباعد الحروف
- **UPPERCASE يحتاج `letter-spacing: 0.05em` إلى `0.1em`** — يمنع التلاصق
- **لا letter-spacing على العربي أبداً** — يكسر الاتصال بين الحروف
- **Lowercase لا يحتاج letter-spacing** — يضر القراءة

---

## الإيقاع العمودي

### line-height
- **استخدم قيمة بلا وحدة:** `line-height: 1.5` (تتناسب)
- **1.5 لنص لاتيني** — افتراضي ممتاز
- **1.8 لنص عربي** — بسبب التشكيل والامتدادات
- **لا وحدة ثابتة أبداً:** لا `line-height: 15pt` (ينكسر عند تغيير الخط)

### Vertical Rhythm
كل المسافات العمودية مضاعفات الـ baseline:

```css
:root {
  --baseline: 1.5rem;
}
body { line-height: 1.5; }
p {
  margin-top: var(--baseline);
  margin-bottom: var(--baseline);
}
h1 {
  font-size: 2.369rem;
  line-height: calc(var(--baseline) * 2);
  margin-top: calc(var(--baseline) * 2);
  margin-bottom: var(--baseline);
}
h2 {
  font-size: 1.777rem;
  line-height: calc(var(--baseline) * 1.5);
  margin-top: calc(var(--baseline) * 2);
  margin-bottom: var(--baseline);
}
```

**القاعدة:** العناوين تحتل مضاعفات دقيقة من الـ baseline — يمكن أن يكون التوزيع غير متماثل (1.5 فوق + 0.5 تحت = 2 خطوط).

---

## سلّم الخطوط (Type Scale)

| النسبة | الاسم | الاستخدام |
|--------|-------|-----------|
| 1.067 | Minor Second | مسافات ضيقة جداً |
| 1.125 | Major Second | واجهات مدمجة |
| 1.200 | Minor Third | UI عام |
| **1.250** | **Major Third** | **UI — تباين واضح بدون مبالغة** |
| **1.333** | **Perfect Fourth** | **مواقع محتوى — تعليم** ← المختار |
| 1.414 | Augmented Fourth | تباين أكبر |
| 1.500 | Perfect Fifth | عناوين درامية |
| 1.618 | Golden Ratio | أقصى درجات التباين |

### التطبيق (Perfect Fourth 1.333)
```css
:root {
  --scale: 1.333;
  --font-xs: 0.75rem;     /* 12px */
  --font-sm: 0.875rem;    /* 14px */
  --font-base: 1rem;      /* 16px */
  --font-lg: 1.333rem;    /* ~21px */
  --font-xl: 1.777rem;    /* ~28px */
  --font-2xl: 2.369rem;   /* ~38px */
  --font-3xl: 3.157rem;   /* ~50px */
}
```

### Responsive Scale
```css
/* Mobile: نسبة أضيق */
:root { --scale: 1.2; }

/* Desktop: نسبة أوسع */
@media (min-width: 48rem) {
  :root { --scale: 1.333; }
}
```

أو باستخدام `clamp()`:
```css
h1 { font-size: clamp(1.8rem, 4vw, 2.369rem); }
h2 { font-size: clamp(1.4rem, 3vw, 1.777rem); }
```

---

## إقران الخطوط (Font Pairing)

- **عائلة واحدة بأوزان مختلفة:** الأبسط والأكثر تماسكاً
- **Serif + Sans-Serif:** الإقران الكلاسيكي
- **حد أقصى: عائلتان** — أكثر = فوضى
- **تسلسل الأوزان:** Roman > Italic > Bold > Small Caps

---

## الخطوط العربية — قواعد خاصة

| القاعدة | السبب |
|---------|-------|
| حجم عربي أكبر 10-15% من اللاتيني | الحروف العربية أصغر بصرياً |
| `line-height: 1.8` للعربي | التشكيل والامتدادات فوق/تحت |
| `letter-spacing: 0` دائماً | الحروف متصلة — spacing يكسرها |
| `font-weight: 400` كحد أدنى | الأوزان الخفيفة صعبة القراءة |
| `hyphens: none` | العربية لا تستخدم الواصلة |
| `text-justify: inter-word` | لا `inter-character` أبداً |
| `word-break: normal` | لا تكسر الكلمات العربية |
| `overflow-wrap: break-word` | للكلمات الطويلة جداً |

### خطوط موصى بها

**عناوين:** Noto Kufi Arabic, Alexandria
**نص القراءة:** Cairo, Tajawal, Noto Naskh Arabic
**Monospace:** Fira Code (للكود)

**Fallback stack:**
```css
font-family: 'Cairo', 'Noto Kufi Arabic', 'Segoe UI', Tahoma, sans-serif;
```

### تطبيق CSS
```css
/* العربي: أكبر وأعلى line-height */
[lang="ar"] {
  font-size: 1.1em; /* 10% أكبر */
  line-height: 1.8;
  letter-spacing: 0;
  hyphens: none;
  word-break: normal;
}

/* الإنجليزي داخل العربي */
[dir="rtl"] [lang="en"],
[dir="rtl"] .ltr-text {
  direction: ltr;
  unicode-bidi: isolate;
}
```

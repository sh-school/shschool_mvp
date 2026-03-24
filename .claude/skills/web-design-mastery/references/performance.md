# الأداء — Designing for Performance (Lara Hogan)

> كل قرار تصميمي هو قرار أداء

---

## Performance Budget

| نوع الصفحة | الحجم الأقصى | زمن التحميل | الطلبات |
|-------------|-------------|-------------|---------|
| Dashboard | < 800KB | < 2s | < 30 |
| جداول/تقارير | < 1.2MB | < 3s | < 40 |
| جوال | < 500KB | < 3s (3G) | < 20 |

**القاعدة:** إذا أضفت عنصراً جديداً (خط، صورة) → وفّر من مكان آخر. الميزانية صفرية المجموع.

---

## تحسين الصور

| التنسيق | الاستخدام | التوفير |
|---------|-----------|---------|
| WebP | صور عامة (بديل JPEG/PNG) | أصغر 25-35% |
| AVIF | الأفضل (2025+) | أصغر من WebP |
| SVG | أيقونات + شعارات | vector — أي حجم |
| JPEG Progressive | صور كبيرة | يظهر تدريجياً |

**تقنيات:**
```html
<!-- تنسيقات متعددة -->
<picture>
  <source srcset="img.avif" type="image/avif">
  <source srcset="img.webp" type="image/webp">
  <img src="img.jpg" alt="وصف" width="800" height="600" loading="lazy">
</picture>

<!-- صورة LCP -->
<img src="hero.webp" alt="..." width="1200" height="600" fetchpriority="high">
```

- `width` + `height` دائماً (يمنع CLS)
- `loading="lazy"` لما تحت الطي
- `fetchpriority="high"` لصورة LCP فقط
- `srcset` + `sizes` للأحجام المتجاوبة
- `display: none` لا يمنع تحميل الصورة — استخدم `<picture>` بدلاً

---

## تحسين الخطوط

| الاستراتيجية | السلوك | الاستخدام |
|-------------|--------|-----------|
| `font-display: swap` | fallback فوراً ثم swap | الافتراضي لنص القراءة |
| `font-display: optional` | 100ms ثم fallback يبقى | صفر CLS — الأفضل للأداء |
| `font-display: fallback` | 100ms مخفي ثم fallback | متوازن |

**Font Subsetting للعربية:**
- الخط العربي الكامل ~900KB → بعد Subsetting ~100KB
- أدوات: glyphhanger, Font Squirrel Generator
- WOFF2 فقط (ضغط مدمج، أفضل 30% من WOFF)

```html
<!-- Preload الخط الأساسي -->
<link rel="preload" href="/fonts/cairo.woff2" as="font" type="font/woff2" crossorigin>
```

```css
@font-face {
  font-family: 'Cairo';
  src: url('/fonts/cairo.woff2') format('woff2');
  font-display: swap;
  unicode-range: U+0600-06FF, U+200C-200F; /* العربية فقط */
}
```

**إدارة الأوزان:**
- حمّل فقط: Regular (400) + Bold (700)
- لا تحمّل Light, Medium, Extra-Bold إلا عند الحاجة الفعلية
- كل وزن = طلب HTTP إضافي

---

## Core Web Vitals (2025)

| المقياس | جيد | يحتاج تحسين | سيئ |
|---------|-----|-------------|-----|
| **LCP** (Largest Contentful Paint) | ≤ 2.5s | 2.5-4s | > 4s |
| **INP** (Interaction to Next Paint) | ≤ 200ms | 200-500ms | > 500ms |
| **CLS** (Cumulative Layout Shift) | ≤ 0.1 | 0.1-0.25 | > 0.25 |
| **FCP** (First Contentful Paint) | ≤ 1.8s | 1.8-3s | > 3s |

### كيف تحسّن كل مقياس:

**LCP:**
- Preload صورة LCP + `fetchpriority="high"`
- CDN (WhiteNoise + Cloudflare)
- Inline critical CSS
- TTFB < 600ms

**INP:**
- كسّر JS الطويل (> 50ms) إلى chunks أصغر
- `requestIdleCallback` للمهام غير العاجلة
- Passive event listeners
- DOM < 1500 عنصر، depth < 32

**CLS:**
- `width` + `height` على كل `<img>` و `<video>`
- `min-height` على حاويات المحتوى الديناميكي
- `font-display: optional` أو مطابقة fallback metrics
- `aspect-ratio` لحاويات الوسائط المتجاوبة

---

## CSS/JS للأداء

**CSS:**
- ملف واحد مضغوط < 30KB (critical path)
- لا `@import` (يسبب تحميل متسلسل) — `<link>` فقط
- Minify (cssnano/PostCSS — توفير 10-15%)
- كل `<link rel="stylesheet">` في `<head>`
- إزالة CSS غير المستخدم (Chrome Coverage tab)

**JavaScript:**
- `defer` (يحترم الترتيب) أو `async` (لا يحترم) — لا blocking أبداً
- Code-splitting: حمّل فقط ما تحتاجه الصفحة الحالية
- Minify بـ Terser/esbuild
- لا third-party scripts غير ضرورية

**الضغط:**
- Brotli أفضل 15-20% من gzip
- gzip يعمل لـ HTML, CSS, JS — لكن ليس WOFF2 (مضغوط أصلاً)

**التخزين المؤقت:**
- `Cache-Control: max-age=31536000` (سنة) للـ static assets
- Cache-busting بـ hash: Django `ManifestStaticFilesStorage`
- `ETag` + `Last-Modified` للتحقق

**Django تحديداً:**
- `WhiteNoise` + `ManifestStaticFilesStorage` للـ static
- `django-compressor` أو `django-imagekit` للصور
- `GZipMiddleware` أو Nginx gzip/Brotli

---

## القياس

| متى | ماذا | الأداة |
|-----|------|--------|
| أثناء التطوير | فحص سريع | Chrome DevTools, Lighthouse |
| كل تغيير كبير | اختبار كامل | WebPagetest |
| شهرياً | تتبع الاتجاه | Lighthouse CI, SpeedCurve |
| أسبوعياً | بيانات مستخدمين حقيقية | Google CrUX |

**قاعدة القياس:** شغّل 5 اختبارات وخذ الوسيط (median).

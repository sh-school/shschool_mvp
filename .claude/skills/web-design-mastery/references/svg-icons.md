# SVG والأيقونات — Pocket Guide to Writing SVG

---

## أساسيات SVG

### الإحداثيات
- `viewBox="0 0 width height"` — يحدد نظام الإحداثيات ويتيح التجاوب
- **دائماً أضف viewBox** — بدونه SVG لا يتجاوب

### أشكال أساسية
```xml
<rect x="0" y="0" width="100" height="50" rx="5"/>
<circle cx="50" cy="50" r="25"/>
<line x1="0" y1="0" x2="100" y2="100" stroke="#333"/>
<polygon points="50,0 100,100 0,100"/>
<path d="M10 80 C 40 10, 65 10, 95 80"/>
```

### تنظيم
- `<g>` — تجميع عناصر مرتبطة
- `<defs>` — تعريفات غير مرسومة (gradients, patterns)
- `<symbol>` — مكون قابل لإعادة الاستخدام (أفضل لـ sprites)
- `<use href="#id">` — إعادة استخدام عنصر معرّف

---

## تحسين SVG

### SVGO/SVGOMG — توفير 30-70%
- إزالة metadata, comments, hidden elements
- تقليل دقة عشرية ≤ 2 منازل
- إزالة `<g>` groups غير ضرورية
- تقصير أسماء IDs

### حافظ على:
- `<title>` و `<desc>` — ضرورية للوصولية
- `viewBox` — ضروري للتجاوب
- ARIA attributes

---

## SVG متجاوب

```css
svg {
  width: 100%;
  height: auto;
}
```

- تحكم بالحجم عبر الحاوية (max-width, Grid, Flexbox)
- `preserveAspectRatio="xMidYMid meet"` — تكبير متناسب (الافتراضي)
- `preserveAspectRatio="none"` — تمدد (استخدمه بحذر)
- `vector-effect="non-scaling-stroke"` — يحافظ على سمك الخط عند التكبير

---

## نظام الأيقونات — SVG Sprites

### بناء الـ Sprite
```html
<!-- includes/icon_sprite.html -->
<svg xmlns="http://www.w3.org/2000/svg" style="display:none">
  <symbol id="icon-home" viewBox="0 0 24 24">
    <path d="M12 3L2 12h3v8h6v-6h2v6h6v-8h3z"/>
  </symbol>
  <symbol id="icon-delete" viewBox="0 0 24 24">
    <path d="M6 19c0 1.1.9 2 2 2h8c1.1 0 2-.9 2-2V7H6v12z"/>
  </symbol>
  <!-- المزيد... -->
</svg>
```

### الاستخدام في Django
```html
<!-- base.html — في نهاية body -->
{% include "includes/icon_sprite.html" %}

<!-- في أي template -->
<svg class="icon" aria-hidden="true" focusable="false">
  <use href="#icon-home"/>
</svg>
```

### CSS للأيقونات
```css
.icon {
  width: 1.25em;
  height: 1.25em;
  fill: currentColor; /* يرث لون النص */
  vertical-align: middle;
}
.icon--sm { width: 1em; height: 1em; }
.icon--lg { width: 1.5em; height: 1.5em; }
```

---

## وصولية SVG

| الحالة | النمط |
|--------|-------|
| أيقونة + نص مرئي (زينة) | `<svg aria-hidden="true" focusable="false">` |
| أيقونة وحدها في زر | `<button aria-label="حذف"><svg aria-hidden="true" focusable="false">...</svg></button>` |
| أيقونة مستقلة ذات معنى | `<svg role="img" aria-labelledby="titleId"><title id="titleId">وصف</title>...</svg>` |

- **دائماً `focusable="false"`** — يمنع tab-into-SVG في IE
- **`aria-hidden="true"`** على كل أيقونة زينة

---

## أنيميشن SVG

### CSS (الأفضل أداءً)
```css
.icon-spin {
  animation: spin 1s linear infinite;
}
@keyframes spin {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}
```

### Self-Drawing Effect
```css
.path-draw {
  stroke-dasharray: 1000;
  stroke-dashoffset: 1000;
  animation: draw 2s ease forwards;
}
@keyframes draw {
  to { stroke-dashoffset: 0; }
}
```

### SMIL (يعمل بدون JS)
```xml
<circle r="10">
  <animate attributeName="r" from="10" to="20" dur="1s" repeatCount="indefinite"/>
</circle>
```

### احترام المستخدم
```css
@media (prefers-reduced-motion: reduce) {
  .icon-spin, .path-draw { animation: none; }
}
```

---

## Django Template Tag (اختياري)
```python
# templatetags/svg_tags.py
from django.utils.html import format_html

@register.simple_tag
def svg_icon(name, css_class="icon", label=None):
    if label:
        return format_html(
            '<svg class="{}" role="img" aria-label="{}" focusable="false">'
            '<use href="#icon-{}"/></svg>',
            css_class, label, name
        )
    return format_html(
        '<svg class="{}" aria-hidden="true" focusable="false">'
        '<use href="#icon-{}"/></svg>',
        css_class, name
    )
```

استخدام:
```html
{% load svg_tags %}
{% svg_icon "home" %}
{% svg_icon "delete" label="حذف" %}
```

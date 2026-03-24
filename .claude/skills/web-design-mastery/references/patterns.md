# أنماط كود — Resilient Web Design + Adaptive Web Design

---

## Progressive Enhancement في Django

Django templates هي Progressive Enhancement بطبيعتها: HTML يُرسل من السيرفر كاملاً.

### النمط الأساسي
```
Layer 0: Django View → HTML كامل (يعمل وحده)
Layer 1: CSS → عرض مرئي (بدونه المحتوى مقروء)
Layer 2: JS/HTMX → تحسين تفاعلي (بدونه النماذج ترسل عادي)
Layer 3: Service Worker → offline (بدونه يعمل online عادي)
```

---

## Ajax Hijacking — النمط الذهبي للنماذج

```html
<!-- يعمل 100% بدون JS -->
<form action="{% url 'quality:create_procedure' %}" method="POST">
  {% csrf_token %}
  {{ form.as_p }}
  <button type="submit">إنشاء</button>
</form>
```

```javascript
// تحسين بـ HTMX (اختياري)
// <form hx-post="{% url 'quality:create_procedure' %}" hx-target="#result">
// أو بـ JS يدوي:
document.querySelector('form').addEventListener('submit', async (e) => {
  e.preventDefault();
  const form = e.target;
  const response = await fetch(form.action, {
    method: 'POST',
    body: new FormData(form),
    headers: { 'X-Requested-With': 'XMLHttpRequest' }
  });
  if (response.ok) {
    // تحديث جزئي للصفحة
  }
});
```

**القاعدة:** إذا عطّلت JS — النموذج لا يزال يعمل.

---

## Feature Detection

### CSS
```css
/* Flexbox fallback */
.grid { display: flex; flex-wrap: wrap; }

/* Grid enhancement */
@supports (display: grid) {
  .grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
    gap: 1rem;
  }
}

/* Container queries */
@supports (container-type: inline-size) {
  .card-wrapper { container-type: inline-size; }
}
```

### JavaScript
```javascript
// Service Worker
if ('serviceWorker' in navigator) {
  navigator.serviceWorker.register('/sw.js');
}

// Intersection Observer (lazy loading)
if ('IntersectionObserver' in window) {
  // lazy load images
} else {
  // load all images immediately
}

// Dialog element
if (typeof HTMLDialogElement !== 'undefined') {
  dialog.showModal();
} else {
  // fallback modal
}
```

### HTML — Cut the Mustard
```html
<!-- متصفحات حديثة (ES modules) -->
<script type="module" src="{% static 'js/modern.js' %}"></script>

<!-- متصفحات قديمة (fallback) -->
<script nomodule src="{% static 'js/legacy.js' %}"></script>
```

---

## أنماط Django Templates

### Semantic HTML
```html
<!-- ✅ صحيح -->
<header class="page-header">
  <nav aria-label="التنقل الرئيسي">
    <ul>
      <li><a href="{% url 'dashboard:home' %}">الرئيسية</a></li>
      <li><a href="{% url 'quality:execution_list' %}" aria-current="page">الجودة</a></li>
    </ul>
  </nav>
</header>
<main id="main">
  <article>
    <h1>إجراءات الجودة</h1>
    <!-- المحتوى -->
  </article>
</main>
<footer><!-- ... --></footer>

<!-- ❌ خاطئ -->
<div class="header">
  <div class="nav">
    <div><a href="/dashboard/">الرئيسية</a></div>
  </div>
</div>
<div class="content">
  <div class="title">إجراءات الجودة</div>
</div>
```

### Forms مع وصولية كاملة
```html
<form action="{% url 'quality:create_procedure' %}" method="POST">
  {% csrf_token %}

  <fieldset>
    <legend>بيانات الإجراء</legend>

    <div class="form-group">
      <label for="id_name">اسم الإجراء <span aria-hidden="true">*</span></label>
      <input id="id_name" name="name" type="text"
             required aria-required="true"
             {% if form.name.errors %}aria-invalid="true" aria-describedby="name-error"{% endif %}>
      {% if form.name.errors %}
        <span id="name-error" class="error" role="alert">{{ form.name.errors.0 }}</span>
      {% endif %}
    </div>
  </fieldset>

  <button type="submit">إنشاء</button>
</form>
```

### جدول بيانات متجاوب
```html
<div class="table-responsive">
  <table>
    <caption>قائمة الطلاب — الصف التاسع</caption>
    <thead>
      <tr>
        <th scope="col">الطالب</th>
        <th scope="col">الدرجة</th>
        <th scope="col">الحالة</th>
      </tr>
    </thead>
    <tbody>
      {% for student in students %}
      <tr>
        <th scope="row">{{ student.name }}</th>
        <td data-label="الدرجة">{{ student.grade }}</td>
        <td data-label="الحالة">
          <span class="badge badge--{{ student.status }}">{{ student.get_status_display }}</span>
        </td>
      </tr>
      {% empty %}
      <tr>
        <td colspan="3" class="empty-state">
          <p>لا يوجد طلاب مسجلون</p>
          <a href="{% url 'students:create' %}" class="btn btn--primary">إضافة طالب</a>
        </td>
      </tr>
      {% endfor %}
    </tbody>
  </table>
</div>
```

### الصور
```html
<!-- صورة عادية -->
<img src="{% static 'img/photo.webp' %}"
     alt="وصف واضح بالعربية"
     width="800" height="600"
     loading="lazy">

<!-- صورة LCP (hero) -->
<img src="{% static 'img/hero.webp' %}"
     alt="..."
     width="1200" height="400"
     fetchpriority="high">

<!-- صورة متعددة التنسيقات -->
<picture>
  <source srcset="{% static 'img/photo.avif' %}" type="image/avif">
  <source srcset="{% static 'img/photo.webp' %}" type="image/webp">
  <img src="{% static 'img/photo.jpg' %}" alt="..." width="800" height="600" loading="lazy">
</picture>
```

---

## أنماط يجب تجنبها

| النمط السيئ | البديل الصحيح |
|------------|--------------|
| `<div onclick="...">` | `<button>` |
| `<a href="#">` كزر | `<button>` |
| Form يعتمد على JS بالكامل | Form يعمل بـ POST + JS تحسين |
| `<table>` للتخطيط | Grid / Flexbox |
| `<div>` لكل شيء | Semantic elements |
| inline styles | CSS classes |
| `<style>` في template | custom.css |
| `!important` لحل تعارض | إصلاح specificity |
| User-Agent sniffing | Feature detection |
| hardcoded URLs | `{% url 'name' %}` / `reverse()` |

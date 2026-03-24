# الوصولية — Just Ask (Shawn Henry)

> دمج الوصولية في كل خطوة تصميم — ليس كخطوة لاحقة

---

## WCAG — المبادئ الأربعة

1. **Perceivable (قابل للإدراك):** بدائل نصية، تباين كافي
2. **Operable (قابل للتشغيل):** لوحة مفاتيح، وقت كافي
3. **Understandable (مفهوم):** نص مقروء، سلوك متوقع
4. **Robust (متين):** يعمل مع التقنيات المساعدة

**الهدف: WCAG 2.1 Level AA** (المعيار العملي).

---

## التباين

| المستوى | نص عادي | نص كبير (18pt+ / 14pt bold) |
|---------|---------|---------------------------|
| **AA (الهدف)** | 4.5:1 | 3:1 |
| AAA | 7:1 | 4.5:1 |
| UI components | 3:1 | 3:1 |
| Focus indicators | 3:1 | 3:1 |

**لا تعتمد على اللون وحده:** أضف أيقونات أو نص بجانب اللون (خطأ = أيقونة + نص أحمر).

**أدوات:** Chrome DevTools contrast checker, WebAIM Contrast Checker, axe DevTools.

---

## لوحة المفاتيح

- **Tab** يصل لكل عنصر تفاعلي بترتيب منطقي
- **لا `outline: none` بدون بديل** — focus ring بتباين 3:1
- `tabindex="0"` لجعل custom elements focusable — لا positive tabindex
- **Escape** يغلق modals
- **Enter/Space** يفعّل الأزرار
- **Arrow keys** للتنقل داخل المجموعات (tabs, menus)

### Skip Link
```html
<a href="#main" class="skip-link">تخطي إلى المحتوى الرئيسي</a>
<!-- ... navigation ... -->
<main id="main">
```
```css
.skip-link {
  position: absolute;
  top: -40px;
  left: 0;
  z-index: 100;
}
.skip-link:focus { top: 0; }
```

### Focus Management
- **Modal:** عند الفتح → focus داخله. عند الإغلاق → focus يعود للزر الأصلي
- **حذف عنصر:** focus ينتقل لأقرب عنصر
- **خطأ نموذج:** focus ينتقل لملخص الأخطاء أو أول حقل خاطئ

---

## Screen Readers + ARIA

### القاعدة الأولى: لا تستخدم ARIA إذا HTML الأصلي يكفي

```html
<!-- ✅ صحيح -->
<button>حفظ</button>

<!-- ❌ خاطئ -->
<div role="button" tabindex="0" onclick="save()">حفظ</div>
```

### Landmarks
```html
<header>    <!-- role="banner" ضمنياً -->
<nav>       <!-- role="navigation" -->
<main>      <!-- role="main" -->
<footer>    <!-- role="contentinfo" -->
```

### Live Regions (للمحتوى الديناميكي)
```html
<!-- رسائل حالة عادية -->
<div aria-live="polite">تم الحفظ بنجاح</div>

<!-- تنبيهات عاجلة -->
<div role="alert">خطأ: الحقل مطلوب</div>
```

### جداول
```html
<table>
  <thead>
    <tr>
      <th scope="col">الطالب</th>
      <th scope="col">الدرجة</th>
    </tr>
  </thead>
  <tbody>
    <tr>
      <th scope="row">أحمد</th>
      <td>95</td>
    </tr>
  </tbody>
</table>
```

---

## النماذج (Forms)

### Labels — كل input يحتاج label مرئي
```html
<!-- ✅ صحيح -->
<label for="student-name">اسم الطالب</label>
<input id="student-name" type="text" required aria-required="true">

<!-- ❌ placeholder ليس بديلاً عن label -->
<input placeholder="اسم الطالب">
```

### تجميع الحقول
```html
<fieldset>
  <legend>معلومات الطالب</legend>
  <label for="name">الاسم</label>
  <input id="name">
  <label for="grade">الصف</label>
  <input id="grade">
</fieldset>
```

### أخطاء النماذج
```html
<!-- الحقل -->
<label for="email">البريد</label>
<input id="email" type="email"
       aria-invalid="true"
       aria-describedby="email-error">
<span id="email-error" role="alert">أدخل بريداً صحيحاً</span>
```

**عند الإرسال:**
1. ملخص أخطاء في الأعلى مع روابط لكل حقل خاطئ
2. نقل focus إلى الملخص
3. `aria-invalid="true"` على كل حقل خاطئ
4. `aria-describedby` يربط الحقل برسالة الخطأ

### Required
```html
<label for="name">الاسم <span aria-hidden="true">*</span></label>
<input id="name" required aria-required="true">
```

---

## اختبار الوصولية

### آلي (يكشف 30-40%)
- axe DevTools (أفضل extension)
- WAVE toolbar
- Lighthouse accessibility audit
- pa11y في CI/CD

### يدوي
1. **كيبورد:** افصل الماوس — تنقل بالكيبورد فقط عبر كل الصفحة
2. **Screen reader:** NVDA (مجاني/Windows) — اختبر المحتوى العربي
3. **Zoom:** 200% بدون scroll أفقي
4. **ألوان:** أوقف الألوان (grayscale) — هل المعلومات واضحة بدون لون؟

### Checklist لكل template في Django
- [ ] كل input فيه label + for/id
- [ ] التباين ≥ 4.5:1
- [ ] Tab order منطقي
- [ ] Focus مرئي
- [ ] كل img فيها alt
- [ ] أخطاء واضحة + aria-describedby
- [ ] Skip link موجود
- [ ] lang + dir صحيحين

---

## التصميم الشامل

**Personas تشمل:**
- معلم يستخدم screen reader
- طالب يتنقل بالكيبورد فقط
- ولي أمر ضعيف البصر

**المبدأ:** صمّم للأطراف والوسط يستفيد. رصيف مائل يخدم الكرسي المتحرك + عربة الأطفال + حقيبة السفر.

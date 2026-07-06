---
name: nplus1-hunter
description: |
  صيّاد استعلامات N+1 في منصة SchoolOS (Django 5.2 + PostgreSQL). يرصد الحلقات — في كود Python
  وفي قوالب Django (خادوم-مُصيَّرة، 1300+ قالب) — التي تعبر علاقة (FK/M2M/عكسية) داخل تكرار
  دون select_related/prefetch_related، ويقترح الإصلاح الدقيق، ويثبته باختبار عدّ استعلامات.
  استخدمها دائماً وتلقائياً عند: مراجعة أداء، بطء صفحة/endpoint، كتابة أو تعديل view/serializer/
  قالب يمرّ على قائمة، أو السؤال "لماذا هذا بطيء/كم استعلاماً؟". Trigger on: N+1, performance,
  slow query, select_related, prefetch_related, بطء, أداء, عدد الاستعلامات, استعلامات كثيرة.
---

# صيّاد N+1 لـ SchoolOS

> N+1 = تُصدر استعلاماً لكل صفّ في حلقة بدل استعلام واحد. على صفحة فيها 200 طالب = 201 استعلام.
> هذا أكبر قاتل أداء في التطبيقات الخادومية-المُصيَّرة. المعيار في المشروع: كل عملية >300ms
> تُعالَج، والاستعلامات تُقلَّل بـ select_related/prefetch_related.

المسار الوحيد: `D:\shschool_mvp` مباشرة.

---

## 1. اصطدها آلياً

```bash
python .claude/skills/nplus1-hunter/scripts/nplus1_scan.py            # Python + قوالب
python .claude/skills/nplus1-hunter/scripts/nplus1_scan.py --app operations
python .claude/skills/nplus1-hunter/scripts/nplus1_scan.py --templates-only
```

الفاحص استدلالي: يرصد المرشّحات (حلقات تعبر علاقة). ليست كلها أخطاءً — أكّد كلّاً منها
بقياس فعلي (القسم 4) قبل الإصلاح.

---

## 2. القاعدة — أيّ أداة لأيّ علاقة

| نوع العلاقة | الأداة | مثال |
|-------------|--------|------|
| ForeignKey / OneToOne (للأمام) | `select_related` (JOIN واحد) | `.select_related("student", "class_group__school")` |
| ManyToMany / علاقة عكسية (`_set`) | `prefetch_related` (استعلام إضافي واحد) | `.prefetch_related("enrollments")` |
| تجميع/عدّ لكل صف | `annotate(Count/Sum)` بدل حلقة | `.annotate(n=Count("enrollments"))` |
| حقل مشتق من علاقة في serializer | جهّزه في الـ selector لا في الـ serializer | — |

المصدر الحقيقي في المشروع يفعل هذا صحيحاً — احتذِ به:
`api/views.py` → `.select_related("student", "class_group")`، `.prefetch_related("enrollments")`،
`.select_related("setup__subject")  # تجنب N+1 عند الوصول لاسم المادة`.

---

## 3. أنماط الإصلاح

### كود Python (view/service/selector)
```python
# ❌ N+1: استعلام لاسم الصف لكل تسجيل
for e in StudentEnrollment.objects.filter(school=school):
    print(e.student.full_name, e.class_group.name)   # كل .student و .class_group = استعلام

# ✅ استعلام ثابت
qs = (StudentEnrollment.objects
      .filter(school=school)
      .select_related("student", "class_group"))
for e in qs:
    print(e.student.full_name, e.class_group.name)
```

### عدّ العلاقات العكسية
```python
# ❌ استعلام عدّ لكل صف
for c in ClassGroup.objects.filter(school=school):
    count = c.enrollments.count()

# ✅ annotate — استعلام واحد
for c in ClassGroup.objects.filter(school=school).annotate(n=Count("enrollments")):
    count = c.n
```

### قالب Django (الأخطر هنا — التصيير يخفي الاستعلامات)
```django
{# ❌ كل {{ s.class_group.name }} داخل الحلقة = استعلام #}
{% for s in students %}{{ s.full_name }} — {{ s.class_group.name }}{% endfor %}
```
الإصلاح **في الـ view** الذي يبني `students`: مرّر queryset فيه
`.select_related("class_group")`. القالب لا يُصلَح في القالب — يُصلَح في مصدره.

### تحسين الـ serializer (DRF)
```python
# ❌ SerializerMethodField ينادي علاقة لكل عنصر
class X(ModelSerializer):
    teacher = serializers.SerializerMethodField()
    def get_teacher(self, obj): return obj.session.teacher.full_name  # N+1

# ✅ جهّز في get_queryset: .select_related("session__teacher")، واقرأ مباشرة
```

---

## 4. أثبِتها بالقياس (لا تُصلح ما لم تَقِسه)

**في اختبار** (النمط المعتمد في المشروع، pytest-django):
```python
def test_list_is_constant_queries(client, teacher_user, many_rows, django_assert_num_queries):
    client.force_authenticate(teacher_user)
    with django_assert_num_queries(4):     # ثابت مهما زاد عدد الصفوف — لو تضخّم فهو N+1
        client.get("/api/v1/students/")
```

**يدوياً في shell**:
```python
from django.test.utils import CaptureQueriesContext
from django.db import connection
with CaptureQueriesContext(connection) as ctx:
    list(build_queryset())
print(len(ctx))          # عدد الاستعلامات الفعلي
```

**في التطوير**: `debug_toolbar` مفعّل في `settings/development.py` — لوحة SQL تُظهر التكرار
والاستعلامات المكرّرة على أي صفحة.

الطريقة الحاسمة: العدد يجب أن يبقى **ثابتاً** عند مضاعفة البيانات. إن نما خطياً مع عدد الصفوف
→ N+1 مؤكّد.

---

## 5. مزالق select_related/prefetch_related

- **إفراط**: `select_related` لعلاقة لا تُقرأ = JOIN بلا فائدة. اجلب ما تعرضه فقط.
- **العمق**: للسلاسل استخدم `__`: `.select_related("session__subject__department")`.
- **مع prefetch متداخل**: `Prefetch("enrollments", queryset=Enrollment.objects.select_related("student"))`.
- **`.only()/.defer()`**: بعد ضبط العلاقات، قلّل الأعمدة المجلوبة على الجداول العريضة.
- **`.values()`**: للتقارير التجميعية، `.values(...).annotate(...)` أسرع من كائنات كاملة.

## 6. الخلاصة التشغيلية
اصطد بالفاحص → أكّد بعدّ الاستعلامات → أصلح في **مصدر** الـ queryset (view/selector) →
ثبّت باختبار `django_assert_num_queries`. لا تُصلح القالب في القالب.

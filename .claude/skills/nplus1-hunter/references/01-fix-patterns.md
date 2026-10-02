# أنماطُ الإصلاح ومزالقُها

متى تقرأ هذا الملف: بعد أن أثبت الاختبارُ أنّ العدد ينمو، وتريد اختيار الأداة الصحيحة وتجنّب ما يُفسد أثرها.

## أيُّ أداةٍ لأيّ علاقة
| ما يُقرأ لكلّ صفّ | الأداة | أثرُها |
|---|---|---|
| FK أو OneToOne للأمام (`e.student`) | `select_related("student", "class_group__school")` | JOIN في الاستعلام نفسِه |
| عكسيٌّ أو M2M (`c.enrollments.all`) | `prefetch_related("enrollments")` | استعلامٌ إضافيٌّ واحدٌ للكلّ |
| عكسيٌّ مصفّى أو بعلاقاته | `Prefetch("enrollments", queryset=…select_related("student"), to_attr="active_enrollments")` | استعلامٌ واحد، وقائمةٌ جاهزة |
| عددٌ أو مجموعٌ لكلّ صفّ | `annotate(n=Count("enrollments", filter=Q(enrollments__is_active=True)))` | صفرُ استعلاماتٍ إضافيّة |
| قيمةٌ واحدةٌ من علاقةٍ بعيدة | `annotate(x=Subquery(...))` أو `F("a__b")` | عمودٌ محسوب |
| تقريرٌ تجميعيّ | `.values(...).annotate(...)` | صفوفٌ خفيفة بلا كائنات |

## مزالقُ تُضيّع الإصلاح
- **فلترٌ بعد prefetch:** `c.enrollments.filter(is_active=True)` و`.count()` و`.order_by()` و`.exists()` على مديرٍ مجلوبٍ مسبقاً تتجاهل الذاكرةَ وتستعلم. اقرأ `.all()` واحسب في بايثون، أو `Prefetch(..., to_attr=...)`، أو `annotate`.
- **`len()` مقابل `count()`:** على قائمةٍ مجلوبةٍ مسبقاً `len(c.enrollments.all())` لا يستعلم، و`c.enrollments.count()` يستعلم.
- **`only()`/`defer()`:** قراءةُ حقلٍ مؤجَّلٍ داخل الحلقة استعلامٌ لكلّ صفّ — أضِف كلَّ ما يقرؤه القالب.
- **`iterator()` مع `prefetch_related`:** في Django 5 يلزمه `chunk_size` وإلّا رفع استثناءً (وثائق Django: `QuerySet.iterator`). والتصديرُ الكبير يمرّ بآليّة التصدير المركزيّة (ADR-0007) لا بحلقةٍ في الطلب.
- **سلاسلُ select_related طويلة** (`a__b__c__d`) على جداول عريضة: JOINاتٌ تُضخّم الصفوف. اجلب ما يُعرض فقط، و`only()` للجداول العريضة بعد التأكّد.
- **`select_related` على علاقةٍ `null=True`:** يعمل (LEFT JOIN)، والقالبُ يجب أن يتحمّل `None`.
- **الترقيم:** الإصلاحُ في `get_queryset` يسري على الصفحة المعروضة وحدها؛ لا تحمّل الكلَّ في بايثون ثمّ تقسّم.

## أمثلة
```python
# خطأ: استعلامان لكلّ شعبة
for c in ClassGroup.objects.filter(school=school, academic_year=year):
    rows.append((c.short_label, c.supervisor.full_name, c.enrollments.filter(is_active=True).count()))

# الصواب: ثلاثةُ استعلاماتٍ ثابتةٌ مهما زادت الشُّعب
qs = (ClassGroup.objects.filter(school=school, academic_year=year)
      .select_related("supervisor")
      .annotate(active=Count("enrollments", filter=Q(enrollments__is_active=True))))
rows = [(c.short_label, c.supervisor.full_name if c.supervisor else "—", c.active) for c in qs]
```

```python
# خطأ: حقلٌ من علاقةٍ في serializer دون تجهيز
class AttendanceSerializer(serializers.ModelSerializer):
    subject = serializers.CharField(source="session.subject.name_ar")

# الصواب: التجهيزُ في get_queryset (كما في api/views.py::AttendanceListView)
StudentAttendance.objects.filter(...).select_related("student", "session__subject", "session__class_group")
```

```django
{# خطأ: القالبُ يعبر علاقتين لكلّ صفّ ومصدرُه بلا تجهيز #}
{% for e in enrollments %}{{ e.student.full_name }} — {{ e.class_group.short_label }}{% endfor %}
{# الصواب: لا تغييرَ في القالب؛ المصدرُ: .select_related("student", "class_group") #}
```

## أنماطٌ مضادّة
- `prefetch_related` لعلاقةٍ أماميّة (يعمل لكن باستعلامٍ إضافيٍّ حيث يكفي JOIN).
- تخزينٌ مؤقّت (cache) لإخفاء N+1 بدل إصلاحه.
- `annotate` بعدّين على علاقتين متعدّدتين في الاستعلام نفسِه دون `distinct=True` — تضاعفُ العدّ.
- «أصلحتُه» بلا اختبارٍ يسقط قبل الإصلاح.

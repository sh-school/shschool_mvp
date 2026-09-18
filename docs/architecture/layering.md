# الطبقاتُ المُلزِمة في SchoolOS

## المبدأ الأساسي

كلُّ طلب HTTP يمرّ عبر ثلاث طبقات، لا رابعة:

```
 Middleware (core/middleware.py)
      ↓
 View Layer (*/views*.py) — بلا منطق عميق
      ↓
 Service Layer (*/services.py) — كلّ ORM و business logic
```

## القوائس الأربع المفروسة

### 1. لا View يزيد على 60 سطر

الحدّ الأقصى هو 60 سطر (بدون decorators). الـ views الأطول تشير إلى منطق معقّد يجب أن يذهب إلى service layer.

مثال:

```python
@login_required
def student_list(request):
    """استدعِ service، اعرض النتيجة — بس."""
    school = request.school
    year = academic_year_for(request)
    
    students = StudentService.list_for_school(
        school=school, year=year, page=request.GET.get("page")
    )
    
    return render(request, "template.html", {"students": students})
```

### 2. لا استدعاءُ ORM يزيد على 5 لكل View

استدعاءات ORM المعدودة:
- `.objects.`
- `.filter()`
- `.annotate()`
- `.aggregate()`
- `select_related()`
- `prefetch_related()`
- `Q(`

إذا تجاوزتَ 5: انقل المنطق إلى service layer.

```python
# صحيح (3 استدعاءات)
students = Student.objects.filter(
    school=school, year=year
).select_related('grade')

# خطأ (6 استدعاءات) — انقل إلى service
students = Student.objects.filter(...)
grades = Grade.objects.filter(...)
classes = ClassGroup.objects.annotate(...).aggregate(...)
# إلخ
```

### 3. `core` لا يستورد من وحدات نازلة

`core/` هي النواة. لا تستورد من:
- analytics
- assessments
- behavior
- clinic
- exam_control
- library
- operations
- parents
- quality
- reports
- staff_affairs
- student_affairs
- transport
- wings
- notifications

إذا احتجتَ إلى نموذج من وحدة نازلة: استخدم lazy import في الدالّة نفسها.

```python
# خطأ
from analytics.models import StudentAnalytics

def some_function():
    analytics = StudentAnalytics.objects.filter(...)

# صحيح
def some_function():
    from analytics.models import StudentAnalytics
    analytics = StudentAnalytics.objects.filter(...)
```

### 4. لا `get_school()` في العروض

استخدم `request.school` بدلاً منه. هو محقون عبر `SchoolContextMiddleware`.

```python
# خطأ
def some_view(request):
    school = get_school()
    ...

# صحيح
def some_view(request):
    school = request.school
    ...
```

## الحارسُ الآلي

ملف `tests/test_layering.py` يفرض هذه القوائس تلقائياً:

```bash
# تشغيل الحارس
python tests/test_layering.py

# تحديثُ baseline بعد تحسينٍ مقصود
python tests/test_layering.py --update-baseline
```

الـ baseline (`tests/layering_baseline.json`) يسجّل الحالة الحالية لكلّ view. الحارسُ يمنع الزيادة فقط.

## مثال: ترحيل منطق من View إلى Service

### قبل الترحيل (منطق في View)

```python
# views.py — سيء
def student_dashboard(request):
    today = timezone.localdate()
    school = request.school
    year = academic_year_for(request)
    
    # 8 استدعاءات ORM هنا!
    students = Student.objects.filter(school=school, year=year)
    absent_today = StudentAttendance.objects.filter(
        student__in=students, date=today, status='absent'
    ).count()
    late_today = StudentAttendance.objects.filter(...).count()
    behavior_today = BehaviorInfraction.objects.filter(...).count()
    # إلخ
    
    return render(request, "dashboard.html", {...})
```

### بعد الترحيل (منطق في Service)

```python
# services.py
class StudentService:
    @staticmethod
    def get_dashboard_context(school, year, today):
        """كلّ الاستعلامات هنا."""
        students = Student.objects.filter(school=school, year=year)
        
        absent_today = StudentAttendance.objects.filter(
            student__in=students, date=today, status='absent'
        ).count()
        late_today = StudentAttendance.objects.filter(...).count()
        behavior_today = BehaviorInfraction.objects.filter(...).count()
        
        return {
            'absent': absent_today,
            'late': late_today,
            'behavior': behavior_today,
        }

# views.py — نظيفة
def student_dashboard(request):
    school = request.school
    year = academic_year_for(request)
    ctx = StudentService.get_dashboard_context(
        school=school, year=year, today=timezone.localdate()
    )
    return render(request, "dashboard.html", ctx)
```

## الملفات المسؤولة

- `tests/test_layering.py` — الحارس
- `tests/layering_baseline.json` — baseline
- `*/services.py` — خدمات كلّ وحدة
- `*/selectors.py` — استعلامات قراءة (QuerySets محضّرة)
- `*/views*.py` — عروض نظيفة (≤60 سطر، ≤5 ORM calls)

## الاستثناءات المعروفة

لا توجد استثناءات. إن وُجد view يتجاوز الحدود: يجب ترحيله.

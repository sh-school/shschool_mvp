---
name: drf-endpoint-scaffold
description: |
  مولّد نقاط طرفية DRF لمنصة SchoolOS وفق معماريتها الطبقية (Clean Architecture: Models →
  Selectors/Services → Serializers → Views → URLs) ومعايير SOLID وأمن OWASP المعتمدة.
  ينتج الطبقات الأربع متّسقة: خدمة سمينة (@transaction.atomic)، serializer نظيف (لا منطق أعمال)،
  view نحيف بصلاحية RBAC وتحسين استعلام (select_related/prefetch_related + pagination)،
  واختبار pytest يشمل الصلاحيات وعدّ الاستعلامات. استخدمها دائماً وتلقائياً عند: إضافة endpoint
  أو REST API جديد، كتابة serializer/view/viewset، توسيع api/، أو السؤال "كيف أبني endpoint
  صحيح؟". Trigger on: DRF, endpoint, REST API, serializer, viewset, api/views, نقطة طرفية, واجهة برمجية.
---

# مولّد نقاط SchoolOS الطرفية

> الهدف: كل endpoint جديد يولد **متّسقاً** مع الطبقات القائمة — لا منطق أعمال في الـ view،
> لا استعلامات N+1، صلاحية RBAC صريحة، واختبار يثبت الأمان والأداء.

المسار الوحيد: `D:\shschool_mvp` مباشرة.

---

## 1. ولّد الهيكل ثم ادمجه

```bash
python .claude/skills/drf-endpoint-scaffold/scripts/scaffold_endpoint.py \
    --app operations --model Subject --name subjects --permission IsTeacherOrAdmin
# للقراءة فقط أضِف: --readonly
```

يُنشئ ملف تجهيز `operations/_scaffold_subjects.py` يحوي الطبقات الأربع (كل كتلة معلّمة بوجهتها
النهائية)، وملف اختبار `operations/tests/test_subjects_api.py`. انقل كل كتلة إلى موضعها ثم احذف
ملف التجهيز. للتفاصيل والأنماط الكاملة: `references/layers.md`.

---

## 2. الطبقات ومسؤولياتها (لا تخلطها — هذا جوهر SOLID هنا)

```
core/models          الكيانات — نحيفة (Skinny Models): حقول + علاقات + خصائص مشتقة فقط
<app>/selectors.py   القراءة — دوال تُرجع QuerySet محسّناً (select/prefetch) وقابلاً لإعادة الاستخدام
<app>/services.py    الكتابة/الأعمال — Fat Service، @staticmethod، @transaction.atomic، idempotent
api/serializers.py   العرض/التحقّق — ModelSerializer فقط؛ لا منطق أعمال ولا وصول DB إضافي
api/views.py         التنسيق — view نحيف: صلاحية + استدعاء selector/service + إرجاع serializer
api/urls.py          التوجيه
api/permissions.py   RBAC — أعد استخدام IsTeacherOrAdmin / IsLeadership / IsSchoolAdmin / ...
```

**القاعدة**: الـ view لا يحسب ولا يكتب في DB مباشرة لأعمال معقّدة — ينادي `services.py`.
الـ serializer لا يستعلم — الـ selector جهّز الاستعلام. كل عملية >300ms → مهمة Celery.

---

## 3. المتطلّبات الإلزامية لكل endpoint في SchoolOS

1. **حصر بالمدرسة**: كل استعلام يبدأ من `School` الحالية (`request.user` → membership). النماذج
   ترث `SchoolScopedModel`؛ لا تُرجع بيانات مدرسة أخرى أبداً (عزل المستأجرين).
2. **صلاحية صريحة**: `permission_classes = [IsAuthenticated, <Role>]` — لا endpoint مفتوح.
   للكائن المفرد أضِف `has_object_permission`.
3. **تحسين الاستعلام**: `select_related` للـ FK، `prefetch_related` للـ M2M/العكسي — في الـ
   selector، ويُتحقّق منه باختبار `django_assert_num_queries`.
4. **الترقيم**: القوائم تستخدم `StandardPagination` (`api/pagination.py`).
5. **حقول آمنة**: لا تعرض PII في serializer دون مبرّر صلاحية (انظر مهارة pdppl-pii-audit).
6. **التوثيق**: `drf-spectacular` مفعّل — أضِف `@extend_schema` عند الحاجة لوصف دقيق.
7. **idempotency**: خدمات الكتابة يجب أن تُعطي نفس النتيجة عند التكرار (لا تُنشئ مكرّراً).

---

## 4. نمط مرجعي مختصر (المصدر الحقيقي: `api/views.py`)

```python
# api/serializers.py — عرض فقط
class SubjectSerializer(serializers.ModelSerializer):
    class Meta:
        model = Subject
        fields = ["id", "name_ar", "code"]

# operations/selectors.py — قراءة محسّنة
def subjects_for_school(school) -> QuerySet[Subject]:
    return Subject.objects.filter(school=school).select_related("school").order_by("name_ar")

# api/views.py — view نحيف
class SubjectListView(generics.ListAPIView):
    serializer_class = SubjectSerializer
    permission_classes = [IsAuthenticated, IsTeacherOrAdmin]
    pagination_class = StandardPagination

    def get_queryset(self):
        return subjects_for_school(_school(self.request))
```

الكتابة تذهب لخدمة:
```python
# operations/services.py
class SubjectService:
    @staticmethod
    @transaction.atomic
    def create(school, *, name_ar: str, code: str) -> Subject:
        obj, _ = Subject.objects.get_or_create(       # idempotent
            school=school, code=code, defaults={"name_ar": name_ar})
        return obj
```

---

## 5. الاختبار جزء من التعريف (لا endpoint بلا اختبار)

كل endpoint يحتاج على الأقل:
- **صلاحية**: مستخدم بلا الدور → 403؛ بالدور → 200.
- **عزل المدرسة**: مستخدم مدرسة A لا يرى بيانات مدرسة B.
- **الأداء**: `django_assert_num_queries(n)` يثبت غياب N+1.
- **الحالة السعيدة + حالة حافة** (فارغ/غير موجود → 404).

النمط الكامل في `references/layers.md`. الإعداد: `pytest`، `DJANGO_SETTINGS_MODULE=shschool.settings.testing`.

## 6. بعد الدمج

```bash
ruff check . && mypy api <app> && pytest <app>/tests/test_<name>_api.py -q
```
حدّث `api/urls.py` بالمسار الجديد، وتأكّد من ظهوره في مخطّط drf-spectacular.

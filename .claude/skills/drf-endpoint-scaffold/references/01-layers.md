# الطبقات: أين يذهب كلُّ شيء

متى تقرأ هذا الملف: حين توزّع كتلَ ملفّ التجهيز على مواضعها، أو تراجع نقطةً لغيرك وتسأل «هل هذا في مكانه؟».

## الخريطة
```
<app>/models.py | <app>/models/   الكيان: حقولٌ وعلاقاتٌ وخصائصُ مشتقّة (نماذجُ نحيفة)
<app>/<domain>_selectors.py        القراءة: دوالُّ تُرجع QuerySet مقيّداً بالمدرسة ومجهَّزاً (select/prefetch)
<app>/services.py | <app>/services/ الكتابة: @transaction.atomic، idempotent، تُنادى من API وأوامر الإدارة وCelery
api/views_<name>.py                serializer العرض والكتابة + view نحيف (السابقة api/views_erasure.py)
api/urls.py                        المسار
api/permissions.py                 الصلاحيّات — أعِد استعمالها، ولا تُنشئ صنفاً لدورٍ له صنف
```
أسماءُ الـselectors على main باسم المجال لا اسمٍ واحد (`behavior/selectors.py`، `reports/selectors.py`، `core/dashboard_selectors.py`، `operations/schedule_selectors.py`، `academic_management/assignment_selectors.py`)، و`operations/services/` حزمةٌ من ملفّات. أضِف إلى القائم في مجالك.
وليس كلُّ `api/views.py` على هذا النمط: نقاطُه القائمة تبني استعلامَها داخل `get_queryset`. النقطةُ الجديدة تتبع الخريطة؛ ولا تُعِد كتابةَ القديمة ضمن طلبك.

## لماذا الفصل (SOLID كما يُطبَّق هنا)
- **مسؤوليّةٌ واحدة:** الـserializer يتحقّق ويعرض ولا يستعلم؛ الـselector يعرف كيف يُجلب؛ الخدمةُ تعرف قواعد العمل؛ الـview ينسّق: صلاحيّة ← selector/خدمة ← serializer.
- **مصدرٌ واحدٌ للاستعلام المحسَّن:** selector واحدٌ يعيد استعمالَه الـAPI والشاشةُ والتقرير، فلا يتفرّق N+1.
- **الخدمةُ قابلةٌ للنداء من خارج الطلب** (أمر إدارة، مهمّة Celery) — ولهذا لا تأخذ `request`.
- **الاعتمادُ على التجريد:** الـview لا يعرف تفاصيلَ ORM المبعثرة؛ يعرف دالّةً وخدمة.

## مثالٌ كامل: قائمةُ خطوط الحافلات (قراءةٌ فقط)
```python
# transport/selectors.py (جديد) — المدرسةُ عبر الحافلة، والحافلةُ تُقرأ في العرض
def bus_routes_for_school(school) -> QuerySet[BusRoute]:
    return (BusRoute.objects.filter(bus__school=school)
            .select_related("bus")
            .order_by("area_name", "id"))          # BusRoute بلا Meta.ordering

# api/views_bus_routes.py
class BusRouteSerializer(serializers.ModelSerializer):
    bus_number = serializers.CharField(source="bus.bus_number")   # مجهَّزٌ بـselect_related

    class Meta:
        model = BusRoute
        fields = ["id", "area_name", "bus_number"]

class BusRouteListView(generics.ListAPIView):
    serializer_class = BusRouteSerializer
    permission_classes = [IsStaffMember]
    pagination_class = StandardPagination

    @extend_schema(summary="خطوط سير الحافلات", tags=["bus-routes"])
    def get(self, *args, **kwargs):
        return super().get(*args, **kwargs)

    def get_queryset(self):
        return bus_routes_for_school(_school(self.request))

# api/urls.py
path("bus-routes/", views_bus_routes.BusRouteListView.as_view(), name="bus-routes-list"),
```
وُلّد هذا بالسكربت ووُزّع واختُبر على نسخةٍ من main في مختبر (PostgreSQL 18): اختباراتُه الأربعة وحارسُ المسارات خضراء.

## الكتابة: خدمةٌ idempotent
```python
class SubjectService:
    @staticmethod
    @transaction.atomic
    def create(school, *, name_ar: str, code: str) -> Subject:
        obj, _created = Subject.objects.get_or_create(
            school=school, code=code, defaults={"name_ar": name_ar})
        return obj
```
- `@transaction.atomic`: الكتابةُ كلُّها أو لا شيء.
- idempotency: إعادةُ الإرسال (ضغطتان، أو إعادةُ محاولة الشبكة) لا تُنشئ صفّاً ثانياً. لكنّ `get_or_create` وحده لا يمنع سباقَ طلبين متزامنين: يلزمه `UniqueConstraint(fields=["school", "code"], …)` في القاعدة (هجرة ← schoolos-migration-guard؛ والقيدُ الفريدُ على جدولٍ قائمٍ تُسقطه البوّابة، فهو قرارُ مراجعة). و`Subject` اليوم بلا هذا القيد و`code` فيه `blank=True`: مفتاحٌ فارغٌ يدمج موادَّ مختلفة. اختر مفتاحاً لا يفرغ.
- الـview يستدعي الخدمة ويعرض بـserializer العرض، ويردّ 201:
```python
def create(self, request, *args, **kwargs):
    ser = SubjectWriteSerializer(data=request.data)
    ser.is_valid(raise_exception=True)
    obj = SubjectService.create(_school(request), **ser.validated_data)
    return Response(SubjectSerializer(obj).data, status=status.HTTP_201_CREATED)
```
- serializer الكتابة: `fields = ["name_ar", "code"]` — التحقّقُ الشكليّ فيه (`validate_code` يقصّ الفراغ ويرفض الفارغ)، وقواعدُ العمل في الخدمة.

## ما لا يدخل الطلب
- ما يزيد عن 300ms (حسابٌ ثقيل، مئاتُ الصفوف تُكتب) ← مهمّةٌ خلفيّة؛ والملفّاتُ المصدَّرة ← الآليّةُ المركزيّة (`core/exports/`، ADR-0007) لا نقطةٌ تبني Excel في الطلب.
- إرسالُ الإشعارات ← طبقةُ الإشعارات القائمة (`notifications/`)، لا من الـview.

## أنماطٌ مضادّة
- `SerializerMethodField` يستعلم لكلّ عنصر.
- منطقُ عملٍ في `validate()` الـserializer (عدٌّ، تحقّقٌ من قاعدة) — مكانُه الخدمة.
- الخدمةُ تأخذ `request` أو تُرجع `Response`.
- selectorٌ ثانٍ ينسخ الأوّلَ بفلترٍ زائد بدل معاملٍ في الأوّل.
- إعادةُ كتابة `api/views.py` كلِّها على نمط الطبقات داخل طلب نقطةٍ واحدة.

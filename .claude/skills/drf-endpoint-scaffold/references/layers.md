# طبقات SchoolOS الكاملة — نمط مرجعي

مثال متكامل لمورد `Subject` في تطبيق `operations`. عمّمه على أي مورد.

## 1. Selector — القراءة (operations/selectors.py)
```python
from __future__ import annotations
from django.db.models import QuerySet
from .models import Subject

def subjects_for_school(school) -> QuerySet[Subject]:
    """قائمة مواد المدرسة، محسّنة ومرتّبة. أعِد استخدامها في views/services/تقارير."""
    return (
        Subject.objects
        .filter(school=school)
        .select_related("school")
        .order_by("name_ar")
    )

def subject_detail(school, subject_id) -> Subject | None:
    return subjects_for_school(school).filter(id=subject_id).first()
```
> لماذا selector منفصل: مصدر واحد لحقيقة الاستعلام المحسّن → لا تكرار ولا N+1 متفرّق،
> وقابل للاختبار وحده.

## 2. Service — الكتابة والأعمال (operations/services.py)
```python
from django.db import transaction
from .models import Subject

class SubjectService:
    @staticmethod
    @transaction.atomic
    def create(school, *, name_ar: str, code: str) -> Subject:
        # idempotent: التكرار لا يُنشئ صفّاً ثانياً
        obj, _created = Subject.objects.get_or_create(
            school=school, code=code, defaults={"name_ar": name_ar}
        )
        return obj

    @staticmethod
    @transaction.atomic
    def rename(subject: Subject, *, name_ar: str) -> Subject:
        subject.name_ar = name_ar
        subject.save(update_fields=["name_ar", "updated_at"])
        return subject
```
> لماذا خدمة: منطق الأعمال قابل للاستدعاء من API وCLI وCelery وأوامر الإدارة دون تكرار،
> والـ `@transaction.atomic` يضمن الذرّية، وemb idempotency يمنع التكرار عند إعادة الإرسال.

## 3. Serializer — العرض/التحقّق فقط (api/serializers.py)
```python
from rest_framework import serializers
from operations.models import Subject

class SubjectSerializer(serializers.ModelSerializer):
    class Meta:
        model = Subject
        fields = ["id", "name_ar", "code"]

class SubjectWriteSerializer(serializers.ModelSerializer):
    class Meta:
        model = Subject
        fields = ["name_ar", "code"]

    def validate_code(self, value: str) -> str:
        if not value.strip():
            raise serializers.ValidationError("الرمز مطلوب")
        return value.strip()
```
> الـ serializer لا ينادي DB إضافياً ولا يحوي منطق أعمال — تحقّق شكلي فقط.

## 4. Views — نحيفة (api/views.py)
```python
from rest_framework import generics, status
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from operations.selectors import subjects_for_school
from operations.services import SubjectService
from .permissions import IsTeacherOrAdmin
from .pagination import StandardPagination
from .serializers import SubjectSerializer, SubjectWriteSerializer

class SubjectListCreateView(generics.ListCreateAPIView):
    permission_classes = [IsAuthenticated, IsTeacherOrAdmin]
    pagination_class = StandardPagination

    def get_serializer_class(self):
        return SubjectWriteSerializer if self.request.method == "POST" else SubjectSerializer

    def get_queryset(self):
        return subjects_for_school(_school(self.request))

    def create(self, request, *args, **kwargs):
        ser = SubjectWriteSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        obj = SubjectService.create(_school(request), **ser.validated_data)
        return Response(SubjectSerializer(obj).data, status=status.HTTP_201_CREATED)
```
> `_school(request)` موجود في api/views.py ويستخرج مدرسة المستخدم. الـ view ينسّق فقط:
> صلاحية → selector/service → serializer. لا حساب هنا.

## 5. URLs (api/urls.py)
```python
path("subjects/", SubjectListCreateView.as_view(), name="subject-list-create"),
```

## 6. الاختبار الكامل (operations/tests/test_subjects_api.py)
```python
import pytest
from django.urls import reverse
from rest_framework.test import APIClient

pytestmark = pytest.mark.django_db

@pytest.fixture
def client():
    return APIClient()

def test_requires_role(client, student_user):
    client.force_authenticate(student_user)          # طالب بلا صلاحية
    assert client.get("/api/v1/subjects/").status_code == 403

def test_teacher_lists_only_own_school(client, teacher_user, subject_a, subject_other_school):
    client.force_authenticate(teacher_user)
    r = client.get("/api/v1/subjects/")
    assert r.status_code == 200
    ids = {row["id"] for row in r.data["results"]}
    assert str(subject_a.id) in ids
    assert str(subject_other_school.id) not in ids   # عزل المدرسة

def test_no_n_plus_one(client, teacher_user, many_subjects, django_assert_num_queries):
    client.force_authenticate(teacher_user)
    with django_assert_num_queries(4):               # ثابت مهما زاد العدد
        client.get("/api/v1/subjects/")

def test_create_is_idempotent(client, teacher_user, school):
    client.force_authenticate(teacher_user)
    payload = {"name_ar": "رياضيات", "code": "MATH"}
    r1 = client.post("/api/v1/subjects/", payload)
    r2 = client.post("/api/v1/subjects/", payload)   # تكرار
    assert r1.status_code == 201
    assert school.subjects.filter(code="MATH").count() == 1
```
> الاختبار يثبت: الصلاحية (403/200)، عزل المدرسة، غياب N+1 (عدد استعلامات ثابت)، وidempotency.
> استخدم factory-boy/Faker للـ fixtures (مثبّتة في requirements-dev.txt).

## SOLID في هذا التصميم
- **S**: كل طبقة مسؤولية واحدة (عرض/قراءة/كتابة/توجيه).
- **O**: تضيف endpoint جديداً دون تعديل القائم (selectors/services تُوسَّع لا تُكسر).
- **L/I**: serializers/permissions صغيرة قابلة للاستبدال.
- **D**: الـ view يعتمد على تجريد الخدمة/الـ selector لا على تفاصيل ORM مبعثرة.

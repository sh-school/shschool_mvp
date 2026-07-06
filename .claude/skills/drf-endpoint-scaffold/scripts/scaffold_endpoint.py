#!/usr/bin/env python3
"""
scaffold_endpoint.py — مولّد نقاط SchoolOS الطرفية وفق المعمارية الطبقية.

الاستخدام:
    python scaffold_endpoint.py --app operations --model Subject --name subjects \
        --permission IsTeacherOrAdmin
    # قراءة فقط:
    python scaffold_endpoint.py --app library --model LibraryBook --name books --readonly

يُنشئ:
    <app>/_scaffold_<name>.py     ملف تجهيز يحوي الطبقات (انقلها لمواضعها ثم احذفه)
    <app>/tests/test_<name>_api.py  اختبار جاهز (صلاحية + عزل مدرسة + N+1 + idempotency)
لا يلمس الملفات المشتركة (serializers/views/urls) تلقائياً — أنت تدمج بوعي.
"""
from __future__ import annotations

import argparse
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]


def staging(app, model, name, perm, readonly) -> str:
    cls = model
    write_layers = "" if readonly else f'''

# ═══════════════ (ب) خدمة الكتابة → انقلها إلى {app}/services.py ═══════════════
from django.db import transaction  # noqa: E402

class {cls}Service:
    @staticmethod
    @transaction.atomic
    def create(school, **data) -> {cls}:
        # idempotent — عدّل مفتاح التفرّد بما يناسب الموديل
        key = data.pop("code", None)
        if key is not None:
            obj, _ = {cls}.objects.get_or_create(school=school, code=key, defaults=data)
            return obj
        return {cls}.objects.create(school=school, **data)


# ═══════════════ (ج) serializer الكتابة → انقلها إلى api/serializers.py ═══════════════
class {cls}WriteSerializer(serializers.ModelSerializer):
    class Meta:
        model = {cls}
        fields = "__all__"  # ← قيّدها بالحقول المسموح إدخالها فقط
'''
    view_cls = "ListAPIView" if readonly else "ListCreateAPIView"
    create_method = "" if readonly else f'''
    def get_serializer_class(self):
        return {cls}WriteSerializer if self.request.method == "POST" else {cls}Serializer

    def create(self, request, *args, **kwargs):
        ser = {cls}WriteSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        obj = {cls}Service.create(_school(request), **ser.validated_data)
        return Response({cls}Serializer(obj).data, status=status.HTTP_201_CREATED)
'''
    return f'''"""
ملف تجهيز مؤقّت لنقطة «{name}» — وزّع الكتل على مواضعها النهائية ثم احذف هذا الملف.
مولّد بمهارة drf-endpoint-scaffold. راجع references/layers.md.
"""
from __future__ import annotations

from django.db.models import QuerySet
from rest_framework import generics, serializers, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from {app}.models import {cls}
from api.permissions import {perm}
from api.pagination import StandardPagination
from api.views import _school  # مستخرج مدرسة المستخدم الحالي


# ═══════════════ (أ) selector القراءة → انقلها إلى {app}/selectors.py ═══════════════
def {name}_for_school(school) -> "QuerySet[{cls}]":
    """قائمة {name} للمدرسة، محسّنة. أضِف select_related/prefetch_related حسب علاقات الموديل."""
    return (
        {cls}.objects
        .filter(school=school)
        # .select_related(...)   ← لكل FL يُقرأ في الـ serializer
        # .prefetch_related(...) ← لكل M2M/علاقة عكسية
        .order_by("-created_at")
    )


# ═══════════════ serializer العرض → انقلها إلى api/serializers.py ═══════════════
class {cls}Serializer(serializers.ModelSerializer):
    class Meta:
        model = {cls}
        fields = "__all__"  # ← قيّدها؛ لا تعرض PII دون مبرّر (راجع pdppl-pii-audit)
{write_layers}

# ═══════════════ (د) view → انقلها إلى api/views.py ═══════════════
class {cls}View(generics.{view_cls}):
    serializer_class = {cls}Serializer
    permission_classes = [IsAuthenticated, {perm}]
    pagination_class = StandardPagination

    def get_queryset(self):
        return {name}_for_school(_school(self.request))
{create_method}

# ═══════════════ (هـ) مسار → أضِفه إلى api/urls.py ═══════════════
# path("{name}/", {cls}View.as_view(), name="{name}"),
'''


def test_file(app, model, name, perm, readonly) -> str:
    idem = "" if readonly else f'''

def test_create_is_idempotent(client, teacher_user, school):
    client.force_authenticate(teacher_user)
    payload = {{}}  # ← عبّئ حقول الإنشاء المطلوبة
    r1 = client.post("/api/v1/{name}/", payload, format="json")
    r2 = client.post("/api/v1/{name}/", payload, format="json")
    assert r1.status_code in (201, 400)  # اضبط بعد تعبئة payload
'''
    return f'''"""اختبار نقطة «{name}» — مولّد بمهارة drf-endpoint-scaffold.
عدّل الـ fixtures بما يوفّره conftest لديك (factory-boy). الإعداد: shschool.settings.testing.
"""
import pytest
from rest_framework.test import APIClient

pytestmark = pytest.mark.django_db


@pytest.fixture
def client():
    return APIClient()


def test_requires_authentication(client):
    assert client.get("/api/v1/{name}/").status_code in (401, 403)


def test_forbidden_without_role(client, student_user):
    client.force_authenticate(student_user)
    assert client.get("/api/v1/{name}/").status_code == 403


def test_allowed_with_role(client, teacher_user):
    client.force_authenticate(teacher_user)
    assert client.get("/api/v1/{name}/").status_code == 200


def test_school_isolation(client, teacher_user, obj_same_school, obj_other_school):
    client.force_authenticate(teacher_user)
    r = client.get("/api/v1/{name}/")
    ids = {{row["id"] for row in r.data.get("results", [])}}
    assert str(obj_same_school.id) in ids
    assert str(obj_other_school.id) not in ids


def test_no_n_plus_one(client, teacher_user, django_assert_num_queries):
    client.force_authenticate(teacher_user)
    with django_assert_num_queries(4):  # اضبط الرقم بعد أول تشغيل
        client.get("/api/v1/{name}/"){idem}
'''


def main() -> int:
    ap = argparse.ArgumentParser(description="مولّد نقاط SchoolOS الطرفية")
    ap.add_argument("--app", required=True)
    ap.add_argument("--model", required=True, help="اسم الـ Model الموجود")
    ap.add_argument("--name", required=True, help="اسم المورد بالمسار (جمع، أحرف صغيرة)")
    ap.add_argument("--permission", default="IsTeacherOrAdmin")
    ap.add_argument("--readonly", action="store_true")
    args = ap.parse_args()

    app_dir = ROOT / args.app
    if not app_dir.is_dir():
        print(f"🔴 التطبيق غير موجود: {app_dir}")
        return 1

    stage = app_dir / f"_scaffold_{args.name}.py"
    stage.write_text(staging(args.app, args.model, args.name, args.permission, args.readonly),
                     encoding="utf-8")

    tests_dir = app_dir / "tests"
    tests_dir.mkdir(exist_ok=True)
    (tests_dir / "__init__.py").touch(exist_ok=True)
    tf = tests_dir / f"test_{args.name}_api.py"
    tf.write_text(test_file(args.app, args.model, args.name, args.permission, args.readonly),
                  encoding="utf-8")

    print("═" * 68)
    print("  ✅ تم توليد نقطة:", args.name)
    print("═" * 68)
    print(f"  📄 التجهيز: {stage.relative_to(ROOT)}")
    print(f"  🧪 الاختبار: {tf.relative_to(ROOT)}")
    print("\n  الخطوات:")
    print("   1) وزّع كتل ملف التجهيز على مواضعها (selectors/services/serializers/views/urls).")
    print("   2) قيّد fields وأضِف select_related/prefetch_related حسب العلاقات.")
    print("   3) احذف ملف التجهيز.")
    print(f"   4) ruff check . && mypy api {args.app} && pytest {tf.relative_to(ROOT)} -q")
    print("═" * 68)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""[LEGAL] كلُّ جدولٍ في `operations` يظهر في `/admin/`، وجداولُ الغياب بقراءةٍ فقط (W-20261004-023، D-201م).

قاعدةُ المالك: يظهر كلُّ جدول. وقرارُ المرحلة أ٣: الجداولُ الحدثيّةُ (الخروجُ والتثبيتان وإخطارُ وليّ الأمر
والعذر والتبديلُ والتعويضُ والإذنُ المؤقّت وسجلُّه) تُكتب بخدماتها وحدَها، وتنبيهُ الغياب يُعدَّل منه الحلُّ فقط، وأسبابُ الغياب الصحّيّة (PDPPL) لا
تُعرض إلا للمشرف الأعلى.
"""

import pytest
from django.apps import apps
from django.contrib import admin
from django.test import RequestFactory

from operations.models import (
    AbsenceAlert,
    AbsenceExcuse,
    CompensatorySession,
    FreeSlotRegistry,
    GuardianContact,
    PeriodConfirmation,
    PermissionAuditLog,
    SectionDayConfirmation,
    TeacherExemption,
    TeacherSwap,
    TemporaryPermission,
)
from tests.conftest import UserFactory

pytestmark = pytest.mark.django_db

SERVICE_TABLES = (
    AbsenceExcuse,
    GuardianContact,
    SectionDayConfirmation,
    PeriodConfirmation,
    TeacherExemption,
    FreeSlotRegistry,
    TeacherSwap,
    CompensatorySession,
    TemporaryPermission,
    PermissionAuditLog,
)


def _request(user):
    request = RequestFactory().get("/admin/")
    request.user = user
    return request


@pytest.fixture
def root():
    return _request(UserFactory(full_name="root", national_id="29000004001", is_superuser=True))


@pytest.fixture
def staff():
    return _request(UserFactory(full_name="staff", national_id="29000004002", is_staff=True))


#: يسجّله فرعُ حزمة الحضور (W-20261004-015/018/019، 0404) بنسخته الكاملة (continued_from وsystem_closed)؛
#: وتسجيلٌ ثانٍ هنا يكسر الإقلاع عند دمج الحزمة. يُزال هذا الاستثناءُ حين تُدمج الحزمةُ في main.
REGISTERED_BY_THE_ATTENDANCE_BUNDLE = {"ClassExit"}


def test_every_operations_model_is_registered_in_admin():
    missing = [
        m.__name__
        for m in apps.get_app_config("operations").get_models()
        if m not in admin.site._registry and m.__name__ not in REGISTERED_BY_THE_ATTENDANCE_BUNDLE
    ]
    assert not missing, f"نماذجُ بلا ModelAdmin: {missing}"


@pytest.mark.parametrize("model", SERVICE_TABLES)
def test_service_written_tables_are_read_only_even_for_a_superuser(model, root):
    model_admin = admin.site._registry[model]
    assert not model_admin.has_add_permission(root)
    assert not model_admin.has_change_permission(root)
    assert not model_admin.has_delete_permission(root)
    assert model_admin.get_actions(root) == {}


@pytest.mark.parametrize("model", SERVICE_TABLES)
def test_changelist_opens_for_a_superuser(model, client):
    client.force_login(
        UserFactory(full_name="root2", national_id="29000004003", is_superuser=True, is_staff=True)
    )
    meta = model._meta
    response = client.get(f"/admin/{meta.app_label}/{meta.model_name}/")
    assert response.status_code == 200


def test_absence_alert_only_the_resolution_is_editable(root):
    model_admin = admin.site._registry[AbsenceAlert]
    assert not model_admin.has_add_permission(root)
    assert not model_admin.has_delete_permission(root)
    assert model_admin.get_actions(root) == {}
    readonly = set(model_admin.get_readonly_fields(root))
    editable = set(model_admin.get_fields(root)) - readonly
    assert editable == {"status", "resolved_by"}
    assert {"gate", "period_start"} <= set(model_admin.list_display)


def test_sensitive_absence_reasons_hidden_without_superuser(root, staff):
    model_admin = admin.site._registry[AbsenceExcuse]
    sensitive = {"kind", "notes", "document", "override_reason", "rejection_reason"}
    assert sensitive <= set(model_admin.get_fields(root))
    shown = set(model_admin.get_fields(staff))
    assert not sensitive & shown
    assert not sensitive & set(model_admin.get_list_display(staff))
    assert not sensitive & set(model_admin.get_list_filter(staff))

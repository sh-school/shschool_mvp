"""[SCHEDULE] صفُّ استثناء القيد يترك أثراً ثابتاً في AuditLog: رمزُ القيد والرتبةُ والوزنُ قبل وبعد ومعرّفُ الصفّ — بلا اسمٍ ولا سببٍ حرّ.

يخفّف الصفُّ فرضَ قيدٍ على المدرسة كلِّها، فلا يكفيه `LogEntry` الافتراضيّ للأدمن (توصيةُ 0105 P3).
"""

import pytest
from django.contrib.admin.sites import AdminSite
from django.test import RequestFactory

from core.models import AuditLog
from operations.admin import ScheduleConstraintOverrideAdmin
from operations.models import ScheduleConstraintOverride

pytestmark = pytest.mark.django_db


@pytest.fixture
def school(db):
    from core.models import School

    return School.objects.create(name="مدرسة الشحانية", code="SHH-OVR")


@pytest.fixture
def vice(db, school):
    from tests.conftest import MembershipFactory, RoleFactory, UserFactory

    user = UserFactory(full_name="النائب الأكاديميّ")
    MembershipFactory(
        user=user, school=school, role=RoleFactory(school=school, name="vice_academic")
    )
    return user


EVENT = "constraint_override_changed"


def _admin_and_request(vice):
    request = RequestFactory().post("/")
    request.user = vice
    return ScheduleConstraintOverrideAdmin(ScheduleConstraintOverride, AdminSite()), request


def _row(school):
    return ScheduleConstraintOverride(
        school=school,
        academic_year="2026-2027",
        code="HC16",
        break_at="dense",
        reason="قرار المالك",
    )


def test_creating_a_row_is_audited_with_code_and_rank_but_no_free_text(school, vice):
    admin, request = _admin_and_request(vice)
    row = _row(school)

    admin.save_model(request, row, None, False)

    log = AuditLog.objects.get(changes__event=EVENT)
    assert log.action == "create"
    assert log.changes["code"] == "HC16"
    assert log.changes["before"] is None
    assert log.changes["after"] == {"break_at": "dense", "weight": None}
    assert log.object_id == str(row.pk)
    assert "قرار المالك" not in str(log.changes) and "قرار المالك" not in log.object_repr


def test_changing_the_rank_records_before_and_after(school, vice):
    admin, request = _admin_and_request(vice)
    row = _row(school)
    admin.save_model(request, row, None, False)

    row.break_at = "relaxed"
    admin.save_model(request, row, None, True)

    log = AuditLog.objects.filter(changes__event=EVENT).order_by("timestamp").last()
    assert log.action == "update"
    assert log.changes["before"]["break_at"] == "dense"
    assert log.changes["after"]["break_at"] == "relaxed"


def test_saving_without_a_change_adds_no_line(school, vice):
    admin, request = _admin_and_request(vice)
    row = _row(school)
    admin.save_model(request, row, None, False)

    admin.save_model(request, row, None, True)

    assert AuditLog.objects.filter(changes__event=EVENT).count() == 1


def test_deleting_a_row_is_audited_with_its_last_values(school, vice):
    admin, request = _admin_and_request(vice)
    row = _row(school)
    admin.save_model(request, row, None, False)
    pk = str(row.pk)

    admin.delete_model(request, row)

    log = AuditLog.objects.filter(changes__event=EVENT, action="delete").get()
    assert log.object_id == pk
    assert log.changes["before"] == {"break_at": "dense", "weight": None}
    assert log.changes["after"] is None
    assert not ScheduleConstraintOverride.objects.filter(pk=pk).exists()


def test_bulk_delete_from_the_list_is_audited_row_by_row(school, vice):
    admin, request = _admin_and_request(vice)
    first, second = _row(school), _row(school)
    second.code = "HC14"
    admin.save_model(request, first, None, False)
    admin.save_model(request, second, None, False)

    admin.delete_queryset(request, ScheduleConstraintOverride.objects.filter(school=school))

    deleted = AuditLog.objects.filter(changes__event=EVENT, action="delete")
    assert sorted(entry.changes["code"] for entry in deleted) == ["HC14", "HC16"]

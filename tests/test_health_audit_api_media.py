"""
tests/test_health_audit_api_media.py — الواجهاتُ وملفّاتُ الأعذار وطلبُ القبول تُدقَّق (CLN-03).

لكلّ موضع: سطرٌ واحدٌ حين تحوي الاستجابةُ بياناً صحّيّاً، بمعرّفاتٍ وأعدادٍ فقط،
ولا سطرَ حين لا بيانَ صحّيّ.
"""

import datetime as dt

import pytest
from django.core.files.base import ContentFile
from django.urls import reverse
from django.utils import timezone

from operations.models import AbsenceActionLog, StudentAttendance
from student_affairs.admission_models import AdmissionApplication
from tests.conftest import MembershipFactory, RoleFactory
from tests.test_absence_excuses import _absent_day
from tests.test_health_audit_excuses import SECRET, _excuse, _lines, _one_line_without_pii
from tests.test_period_register import (  # noqa: F401 — التجهيزاتُ نفسُها
    kids,
    klass,
    subjects,
    supervisor,
    teacher,
    year,
)

pytestmark = [pytest.mark.django_db, pytest.mark.pin_clock]


def _get(client_as, user, url):
    response = client_as(user).get(url)
    assert response.status_code == 200
    return response


@pytest.mark.parametrize("kind, expected", [("medical", 1), ("family", 0)])
def test_attendance_apis_audit_medical_excuse(
    client_as, school, klass, kids, teacher, supervisor, principal_user, kind, expected
):
    day = timezone.localdate() - dt.timedelta(days=1)
    _absent_day(school, klass, kids[0], teacher, supervisor, day=day, count=1)
    StudentAttendance.objects.filter(student=kids[0]).update(excuse_type=kind)
    # واجهةُ غياب الطالب تشترط عضويّةً نشطةً في المدرسة، وتجهيزةُ kids قيدُ شعبةٍ فقط.
    MembershipFactory(user=kids[0], school=school, role=RoleFactory(school=school, name="student"))

    _get(client_as, principal_user, f"/api/v1/attendance/?student_id={kids[0].id}")
    _get(client_as, principal_user, f"/api/v1/students/{kids[0].id}/attendance/")

    for screen in ("واجهة سجل الحضور (API)", "واجهة غياب طالب (API)"):
        assert len(_lines(principal_user, screen)) == expected
        if expected:
            line = _one_line_without_pii(principal_user, screen, kids[0])
            assert line.object_id == str(kids[0].id)


def _action(school, student, by, status, note=""):
    return AbsenceActionLog.objects.create(
        school=school,
        student=student,
        absence_date=timezone.localdate(),
        action_kind="other",
        status=status,
        note=note,
        acted_by=by,
    )


def _absent_today(school, klass, kid, teacher, supervisor):
    _absent_day(school, klass, kid, teacher, supervisor, day=timezone.localdate(), count=2)


@pytest.mark.parametrize(
    "status, note, expected",
    [("sick_leave_received", "", 1), ("done", SECRET, 1), ("done", "", 0)],
)
def test_absence_actions_audits_sick_leave_and_note(
    client_as, school, klass, kids, teacher, supervisor, principal_user, status, note, expected
):
    _absent_today(school, klass, kids[0], teacher, supervisor)
    _action(school, kids[0], principal_user, status, note)

    response = _get(client_as, principal_user, reverse("absence_actions"))

    assert [row["student"] for row in response.context["rows"] if row["action"]] == [kids[0]]
    assert len(_lines(principal_user, "متابعة إجراءات الغياب")) == expected
    if expected:
        _one_line_without_pii(principal_user, "متابعة إجراءات الغياب", kids[0])


@pytest.mark.parametrize("status, expected", [("sick_leave_received", 1), ("done", 0)])
def test_dashboard_audits_sick_leave_panel(
    client_as, school, klass, kids, teacher, supervisor, principal_user, status, expected
):
    _absent_today(school, klass, kids[0], teacher, supervisor)
    _action(school, kids[0], principal_user, status)

    response = _get(client_as, principal_user, reverse("student_affairs:dashboard"))

    assert len(response.context["panels"]["absence"]["sick_leave"]) == expected
    assert len(_lines(principal_user, "لوحة استلام الإجازات المرضية")) == expected
    if expected:
        _one_line_without_pii(principal_user, "لوحة استلام الإجازات المرضية", kids[0])


@pytest.mark.parametrize("health_status, expected", [(SECRET, 1), ("", 0)])
def test_admission_detail_audits_health_status(
    client_as, school, principal_user, student_user, health_status, expected
):
    application = AdmissionApplication.objects.create(
        school=school,
        academic_year="2026-2027",
        student_name=student_user.full_name,
        student_national_id="29000000001",
        applicant_name="مقدّم الطلب",
        applicant_national_id="29000000002",
        health_status=health_status,
    )
    url = reverse("student_affairs:admission_detail", args=[application.pk])

    _get(client_as, principal_user, url)

    assert len(_lines(principal_user, "تفاصيل طلب الالتحاق")) == expected
    if expected:
        line = _one_line_without_pii(principal_user, "تفاصيل طلب الالتحاق", student_user)
        assert line.object_id == str(application.pk)


def _open_file(client_as, user, field):
    return _get(client_as, user, reverse("serve_db_file", kwargs={"name": field.name}))


@pytest.mark.parametrize("kind, expected", [("medical", 1), ("family", 0)])
def test_dbmedia_audits_medical_excuse_document(
    client_as, school, kids, supervisor, kind, expected
):
    excuse = _excuse(school, kids[0], supervisor, kind)
    excuse.document.save("report.pdf", ContentFile(b"%PDF-1.4 fake"))

    _open_file(client_as, supervisor, excuse.document)

    assert len(_lines(supervisor, "ملف عذر غياب")) == expected
    if expected:
        line = _one_line_without_pii(supervisor, "ملف عذر غياب", kids[0])
        assert line.object_id == str(excuse.pk)
        assert excuse.document.name not in f"{line.object_repr} {line.changes}"


@pytest.mark.parametrize("excuse_type, expected", [("medical", 1), ("", 1), ("family", 0)])
def test_dbmedia_audits_attendance_excuse_file(
    client_as, school, klass, kids, teacher, supervisor, excuse_type, expected
):
    _absent_day(school, klass, kids[0], teacher, supervisor, count=1)
    row = StudentAttendance.objects.get(student=kids[0])
    row.excuse_type = excuse_type
    row.excuse_file.save("slip.pdf", ContentFile(b"%PDF-1.4 fake"))

    _open_file(client_as, supervisor, row.excuse_file)

    assert len(_lines(supervisor, "ملف عذر غياب")) == expected
    if expected:
        line = _one_line_without_pii(supervisor, "ملف عذر غياب", kids[0])
        assert line.object_id == str(row.pk)

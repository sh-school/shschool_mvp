"""
tests/test_health_audit_excuses.py — عرضُ الأعذار والملاحظات الصحّيّة يُدقَّق (CLN-03).

لكلّ موضع: سطرٌ واحدٌ حين تحوي الاستجابةُ بياناً صحّيّاً، بمعرّفاتٍ وأعدادٍ فقط،
ولا سطرَ حين لا بيانَ صحّيّ.
"""

import datetime as dt

import pytest
from django.urls import reverse
from django.utils import timezone

from assessments.models import StudentAssessmentGrade
from core.models import AuditLog
from operations.models import AbsenceExcuse, ExitPermit, StudentAttendance
from student_info.models import StudentNote
from tests.test_absence_excuses import _absent_day, vice_admin  # noqa: F401
from tests.test_grade_save_all import assessment  # noqa: F401 — فكسترُ التقييم نفسُه
from tests.test_period_register import (  # noqa: F401 — التجهيزاتُ نفسُها
    SUNDAY,
    kids,
    klass,
    subjects,
    supervisor,
    teacher,
    year,
)

pytestmark = [pytest.mark.django_db, pytest.mark.pin_clock]

SECRET = "نصٌّ صحّيٌّ سرّيّ"


def _lines(user, screen):
    return [
        line
        for line in AuditLog.objects.filter(user=user, action="view")
        if (line.changes or {}).get("screen") == screen
    ]


def _one_line_without_pii(user, screen, student, *, rows=1):
    (line,) = _lines(user, screen)
    assert line.changes == {"screen": screen, "rows": rows}
    # فاصلٌ «|» كي لا يطابق «طالب 0» نصَّ «عذر الطالب» متبوعاً بمعرّفٍ يبدأ بـ0
    blob = f"{line.object_repr}|{line.object_id}|{line.changes}"
    for secret in (student.full_name, SECRET):
        assert secret not in blob
    return line


def _get(client_as, user, url):
    response = client_as(user).get(url)
    assert response.status_code == 200
    return response


def _excuse(school, student, by, kind, status="pending", day=SUNDAY):
    return AbsenceExcuse.objects.create(
        school=school,
        student=student,
        date_from=day,
        date_to=day,
        kind=kind,
        notes=SECRET,
        granted_by=by,
        status=status,
    )


@pytest.mark.parametrize("category, expected", [("nurse", 1), ("teacher", 0)])
def test_student_file_and_notes_list_audit_nurse_notes(
    client_as, school, principal_user, student_user, enrolled_student, category, expected
):
    year_name = enrolled_student.class_group.academic_year
    StudentNote.objects.create(
        school=school,
        student=student_user,
        category=category,
        academic_year=year_name,
        occurred_on=timezone.localdate(),
        title=SECRET,
        body=SECRET,
        created_by=principal_user,
    )
    file_url = reverse("student_info:student_file", args=[student_user.id])
    list_url = reverse("student_info:notes", args=[category])

    _get(client_as, principal_user, f"{file_url}?year={year_name}")
    _get(client_as, principal_user, f"{list_url}?year={year_name}")

    for screen in ("ملاحظات الممرض في ملف الطالب", "قائمة ملاحظات الممرض"):
        assert len(_lines(principal_user, screen)) == expected
        if expected:
            _one_line_without_pii(principal_user, screen, student_user)


@pytest.mark.parametrize("kind, expected", [("medical", 1), ("family", 0)])
def test_student_events_audits_medical_excuse(
    client_as, school, seeded_calendar, klass, kids, supervisor, kind, expected
):
    _excuse(school, kids[0], supervisor, kind)

    _get(client_as, supervisor, reverse("wings:student_events", args=[klass.id, kids[0].id]))

    assert len(_lines(supervisor, "تصحيح وعذر الطالب")) == expected
    if expected:
        line = _one_line_without_pii(supervisor, "تصحيح وعذر الطالب", kids[0])
        assert line.object_id == str(kids[0].id)


@pytest.mark.parametrize("kind, expected", [("medical", 1), ("family", 0)])
def test_absence_file_audits_medical_excuse(
    client_as, school, seeded_calendar, klass, kids, teacher, supervisor, kind, expected
):
    _absent_day(school, klass, kids[0], teacher, supervisor)
    excuse = _excuse(school, kids[0], supervisor, kind, status="accepted")
    StudentAttendance.objects.filter(student=kids[0]).update(excuse_type=kind, excuse=excuse)

    response = _get(client_as, supervisor, reverse("wings:absence_file", args=[kids[0].id]))

    assert any(day.excuse for day in response.context["days"])
    assert len(_lines(supervisor, "ملف غياب الطالب")) == expected
    if expected:
        _one_line_without_pii(supervisor, "ملف غياب الطالب", kids[0])


@pytest.mark.parametrize("kind, expected", [("medical", 1), ("family", 0)])
def test_excuse_requests_audits_medical_excuse(
    client_as,
    school,
    kids,
    supervisor,
    vice_admin,  # noqa: F811
    kind,
    expected,
):
    _excuse(school, kids[0], supervisor, kind)

    _get(client_as, vice_admin, reverse("wings:excuse_requests"))

    assert len(_lines(vice_admin, "أعذار بانتظار النائب")) == expected
    if expected:
        _one_line_without_pii(vice_admin, "أعذار بانتظار النائب", kids[0])


@pytest.mark.parametrize("excuse_type, expected", [("illness", 1), ("force_majeure", 0)])
def test_excuse_queue_audits_illness_excuse(
    client_as,
    vice_admin,  # noqa: F811
    assessment,  # noqa: F811
    student_user,
    enrolled_student,
    excuse_type,
    expected,
):
    StudentAssessmentGrade.objects.create(
        school=assessment.school,
        assessment=assessment,
        student=student_user,
        is_absent=True,
        is_excused=True,
        excuse_type=excuse_type,
        excuse_reference=SECRET,
        excuse_decided_by=vice_admin,
        excuse_decided_at=timezone.now(),
    )

    response = _get(client_as, vice_admin, reverse("excuse_queue"))

    assert list(response.context["decided"])
    assert len(_lines(vice_admin, "أعذار الاختبارات")) == expected
    if expected:
        _one_line_without_pii(vice_admin, "أعذار الاختبارات", student_user)


@pytest.mark.parametrize("reason, expected", [("medical", 1), ("family", 0)])
def test_exit_permit_list_audits_medical_reason(
    client_as, school, klass, kids, supervisor, reason, expected
):
    ExitPermit.objects.create(
        school=school,
        student=kids[0],
        class_group=klass,
        sequence=1,
        reason=reason,
        note=SECRET,
        exit_at=timezone.make_aware(dt.datetime.combine(SUNDAY, dt.time(11, 0))),
        requested_by=supervisor,
        status="issued",
    )
    url = f"{reverse('wings:exit_permit_list')}?date={SUNDAY.isoformat()}"

    response = _get(client_as, supervisor, url)

    assert SECRET in response.content.decode()
    assert len(_lines(supervisor, "قائمة أذونات الخروج")) == expected
    if expected:
        _one_line_without_pii(supervisor, "قائمة أذونات الخروج", kids[0])

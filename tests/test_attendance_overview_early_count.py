"""عدّاد «حاضرون» في نظرة الحضور — من حضور الحصّتين الأولى والثانية (W-20261008-027).

قرار المالك 2026-10-09: من حضر إحدى الحصّتين فهو حاضر، والغائبُ من غاب عنهما معاً، والطالبُ يُعدّ مرّةً.
"""

import datetime as dt

import pytest
from django.urls import reverse

from core.models import Wing
from operations.models import Session, StudentAttendance
from student_affairs.selectors import early_attendance_counts
from tests.attendance_fixtures import *  # noqa: F403
from tests.conftest import (
    ClassGroupFactory,
    MembershipFactory,
    RoleFactory,
    StudentEnrollmentFactory,
    UserFactory,
)
from wings.scope import StudentScope

pytestmark = pytest.mark.django_db

_N = iter(range(29000000100, 29000000999))


def _kid(klass):
    student = UserFactory(full_name="طالب", national_id=str(next(_N)))
    StudentEnrollmentFactory(student=student, class_group=klass, enrolled_at=ENROLLED)  # noqa: F405
    return student


def _lesson(school, klass, teacher, number, day=SUNDAY):  # noqa: F405
    return Session.objects.create(
        school=school,
        class_group=klass,
        teacher=teacher,
        date=day,
        start_time=dt.time(6 + number, 0),
        end_time=dt.time(6 + number, 45),
        period_number=number,
        status="completed",
    )


def _mark(school, session, student, status, excuse=""):
    StudentAttendance.objects.create(
        school=school, session=session, student=student, status=status, excuse_type=excuse
    )


def _teacher():
    return UserFactory(full_name="معلّم", national_id=str(next(_N)))


def _open(school):
    return StudentScope(school=school, wing_ids=None)


def test_present_in_either_period_is_present(school, klass, teacher, bells):
    first, second = _lesson(school, klass, teacher, 1), _lesson(school, klass, teacher, 2)
    late_then_gone, first_only, second_only = _kid(klass), _kid(klass), _kid(klass)
    _mark(school, first, late_then_gone, "late")
    _mark(school, second, late_then_gone, "absent")
    _mark(school, first, first_only, "present")
    _mark(school, second, first_only, "absent")
    _mark(school, first, second_only, "absent")
    _mark(school, second, second_only, "present")

    summary = early_attendance_counts(school, SUNDAY, _open(school))["summary"]

    assert (summary["total"], summary["present"], summary["absent"]) == (3, 3, 0)
    assert summary["late"] == 1


def test_absent_in_both_is_absent_and_counted_once(school, klass, teacher, bells):
    first, second = _lesson(school, klass, teacher, 1), _lesson(school, klass, teacher, 2)
    gone, excused = _kid(klass), _kid(klass)
    for session in (first, second):
        _mark(school, session, gone, "absent")
        _mark(school, session, excused, "absent", excuse="medical")

    summary = early_attendance_counts(school, SUNDAY, _open(school))["summary"]

    assert (summary["total"], summary["absent"], summary["excused"]) == (2, 2, 1)
    assert summary["present"] == 0 and summary["pct"] == 0


def test_before_any_early_record_the_rate_is_empty_not_zero(school, klass, teacher, bells):
    third = _lesson(school, klass, teacher, 3)
    _mark(school, third, _kid(klass), "present")

    summary = early_attendance_counts(school, SUNDAY, _open(school))["summary"]

    assert summary["total"] == 0 and summary["pct"] is None


def test_section_totals_add_up_to_the_wing(school, year, wing, klass, teacher, bells):
    other = ClassGroupFactory(
        school=school, grade="G7", section="2", level_type="prep", academic_year=year, wing=wing
    )
    for group, statuses in ((klass, ("present", "absent")), (other, ("absent",))):
        tutor = _teacher()
        first, second = _lesson(school, group, tutor, 1), _lesson(school, group, tutor, 2)
        for status in statuses:
            student = _kid(group)
            _mark(school, first, student, status)
            _mark(school, second, student, status)

    wings = early_attendance_counts(school, SUNDAY, _open(school))["wings"]

    assert len(wings) == 1
    sections = wings[0]["sections"]
    assert [s["counts"]["total"] for s in sections] == [2, 1]
    for key in ("total", "present", "absent"):
        assert wings[0]["counts"][key] == sum(s["counts"][key] for s in sections)


def test_a_wing_bound_scope_sees_only_its_wing(school, year, wing, klass, teacher, bells):
    stranger_wing = Wing.objects.create(
        school=school, code="w2", name="جناح 2", academic_year=year, supervisor=teacher
    )
    stranger = ClassGroupFactory(
        school=school, grade="G8", section="2", level_type="prep", academic_year=year,
        wing=stranger_wing,
    )  # fmt: skip
    mine, theirs = _kid(klass), _kid(stranger)
    for group, student in ((klass, mine), (stranger, theirs)):
        _mark(school, _lesson(school, group, _teacher(), 1), student, "present")

    scope = StudentScope(school=school, wing_ids=frozenset({wing.pk}), year=year)
    summary = early_attendance_counts(school, SUNDAY, scope)["summary"]

    assert summary["total"] == 1


@pytest.mark.pin_clock
def test_the_page_renders_the_early_definition(
    client_as, school, seeded_calendar, klass, teacher, bells, monkeypatch
):
    from django.utils import timezone

    monkeypatch.setattr(timezone, "localdate", lambda *a, **k: SUNDAY)
    first, second = _lesson(school, klass, teacher, 1), _lesson(school, klass, teacher, 2)
    student = _kid(klass)
    _mark(school, first, student, "absent")
    _mark(school, second, student, "present")
    principal = UserFactory(full_name="مدير", national_id="29000000001")
    MembershipFactory(
        user=principal, school=school, role=RoleFactory(school=school, name="principal")
    )

    page = client_as(principal).get(reverse("student_affairs:attendance_overview"))

    assert page.status_code == 200
    assert page.context["summary"]["present"] == 1 and page.context["pct_label"] == "100%"
    assert "الحصّتين الأولى أو الثانية".encode() in page.content
    assert page.context["wing_rows"][0]["sections"]

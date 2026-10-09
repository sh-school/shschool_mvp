"""W-20261009-003 — جدولُ الشعبة لكلّ التواريخ: قراءةُ الماضي بتصحيحٍ مسبَّب، والمستقبلُ للقراءة فقط."""

import datetime as dt
import itertools

import pytest
from django.urls import reverse

from operations.attendance_policy import can_correct_grid
from operations.services import class_grid as grid
from tests.attendance_fixtures import *  # noqa: F401,F403
from tests.attendance_fixtures import SUNDAY, _staff
from tests.test_class_grid import (  # noqa: F401  (fixtures)
    _cells,
    _grid_on,
    _save,
    assigned,
    clock,
    kids,
    subject,
)

pytestmark = pytest.mark.django_db

THURSDAY_BEFORE = SUNDAY - dt.timedelta(days=7)  # الأحدُ السابق: له جرسُ اليوم نفسُه
MONDAY_AFTER = SUNDAY + dt.timedelta(days=1)
FRIDAY_BEFORE = SUNDAY - dt.timedelta(days=2)


_COUNTER = itertools.count(1)


def _principal(school):
    return _staff(school, "principal", "مدير", f"2900000{next(_COUNTER):04d}9")


def test_a_past_day_opens_for_reading_with_all_columns_past(
    client_as, school, assigned, kids, clock
):
    response = client_as(_principal(school)).get(
        reverse("class_grid", args=[assigned.id]), {"date": THURSDAY_BEFORE.isoformat()}
    )
    assert response.status_code == 200
    page = response.context["grid_page"]
    assert page.day == THURSDAY_BEFORE
    assert page.columns and all(c.state == "past" for c in page.columns)
    assert page.correction_mode and page.current is None


def test_a_future_day_is_read_only_for_everyone(client_as, school, assigned, kids, clock):
    response = client_as(_principal(school)).get(
        reverse("class_grid", args=[assigned.id]), {"date": MONDAY_AFTER.isoformat()}
    )
    assert response.status_code == 200
    page = response.context["grid_page"]
    assert all(c.state == "future" and not c.writable for c in page.columns)
    denied = _save(
        client_as(_principal(school)),
        assigned,
        1,
        [_cells(kids[0], "absent")],
        date=MONDAY_AFTER.isoformat(),
        reason="x",
    )
    assert denied.status_code == 403


def test_a_day_without_school_and_a_bad_date_are_404(client_as, school, assigned, clock):
    client = client_as(_principal(school))
    url = reverse("class_grid", args=[assigned.id])
    assert client.get(url, {"date": FRIDAY_BEFORE.isoformat()}).status_code == 404
    assert client.get(url, {"date": "not-a-date"}).status_code == 404


def test_the_past_is_corrected_with_a_reason_only(client_as, school, assigned, kids, clock):
    client = client_as(_principal(school))
    day = THURSDAY_BEFORE.isoformat()
    missing = _save(client, assigned, 1, [_cells(kids[0], "absent")], date=day)
    assert missing.status_code == 403 and missing.json()["reason"] == "reason_required"
    saved = _save(client, assigned, 1, [_cells(kids[0], "absent")], date=day, reason="تصحيحٌ بسبب")
    assert saved.status_code == 200 and saved.json()["saved"]


def test_the_teacher_reads_the_past_but_cannot_write_it(client_as, teacher, assigned, kids, clock):
    client = client_as(teacher)
    day = THURSDAY_BEFORE.isoformat()
    assert client.get(reverse("class_grid", args=[assigned.id]), {"date": day}).status_code == 200
    refused = _save(client, assigned, 1, [_cells(kids[0], "absent")], date=day, reason="س")
    assert refused.status_code == 403


def test_the_corrector_policy_covers_the_past_but_not_the_future(assigned, holder, clock):
    now = SUNDAY
    from tests.attendance_fixtures import at

    assert can_correct_grid(holder, assigned, THURSDAY_BEFORE, now=at(9, 0))
    assert not can_correct_grid(holder, assigned, MONDAY_AFTER, now=at(9, 0))
    assert now  # يوم الأحد مرجعٌ


def test_the_grid_url_for_any_date_to_the_grid_for_any_date(school, assigned, kids, clock):
    principal = _principal(school)
    today_link = grid.grid_url_for_class(principal, assigned)
    past_link = grid.grid_url_for_class(principal, assigned, THURSDAY_BEFORE)
    assert today_link == reverse("class_grid", args=[assigned.id])
    assert past_link == f"{today_link}?date={THURSDAY_BEFORE.isoformat()}"
    # يومٌ بلا دراسةٍ: يبقى الكشفُ لا 404
    assert grid.grid_url_for_class(principal, assigned, FRIDAY_BEFORE) is None


def test_a_substitute_covering_the_class_today_opens_and_writes_the_grid(
    client_as, school, assigned, kids, teacher, other_teacher, clock
):
    """البديلُ المعيَّنُ لحصّةٍ من الشعبة اليومَ يفتح جدولها ويكتب؛ وغيرُ المعيَّن 404؛ وغداً لا تغطية."""
    from core.academic_calendar import academic_year_for_school
    from operations.models import ScheduleSlot, SubstituteAssignment, TeacherAbsence

    slot = ScheduleSlot.objects.create(
        school=school,
        teacher=teacher,
        class_group=assigned,
        day_of_week=0,
        period_number=1,
        start_time=dt.time(7, 10),
        end_time=dt.time(7, 55),
        academic_year=academic_year_for_school(school),
    )
    client = client_as(other_teacher)
    url = reverse("class_grid", args=[assigned.id])
    assert client.get(url).status_code == 404

    absence = TeacherAbsence.objects.create(school=school, teacher=teacher, date=SUNDAY)
    SubstituteAssignment.objects.create(
        school=school, absence=absence, slot=slot, substitute=other_teacher
    )
    assert client.get(url).status_code == 200
    assert assigned in grid.classes_for(other_teacher, school)
    assert _save(client, assigned, 1, [_cells(kids[0], "absent")]).status_code == 200
    tomorrow = SUNDAY + dt.timedelta(days=1)
    assert client.get(url, {"date": tomorrow.isoformat()}).status_code == 404

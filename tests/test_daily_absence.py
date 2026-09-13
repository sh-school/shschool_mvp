"""غيابُ اليوم — طالبٌ في سطر، ووسمُ الرفع الوزاريّ (قرارُ 2026-09-13).

حلّ محلَّ «سجلّات الحضور والغياب» التي كانت تعدّ السجلّات لا الطلاب: الغائبُ سبعَ
حصصٍ سبعةُ أسطر. والوسمُ لمن غاب الأولى والثانية — بعذرٍ أو بدونه — ولا وسمَ على
رصدٍ ناقص. ويشمل شُعبَ التربية الخاصّة خارج الأجنحة برصد معلّميها.
"""

import pytest
from django.urls import reverse

from operations.daily_absence import daily_report
from tests.test_period_register import (  # noqa: F401 — التجهيزاتُ نفسُها
    SUNDAY,
    _confirm,
    _periods,
    kids,
    klass,
    supervisor,
    teacher,
    year,
)

pytestmark = pytest.mark.django_db


def test_a_student_absent_all_day_is_one_row_not_seven(
    school, seeded_calendar, klass, kids, teacher, supervisor
):
    for session in _periods(school, klass, teacher, 7):
        _confirm(klass, session, {kids[0]: "absent"}, supervisor)

    report = daily_report(school, SUNDAY)

    assert [r.student for r in report.rows] == [kids[0]]
    (row,) = report.rows
    assert (row.absent_periods, row.late_periods, len(row.slots)) == (7, 0, 7)
    assert row.ministry_flag == "unexcused"
    assert report.students_recorded == 4


def test_absent_first_two_periods_is_flagged_for_the_ministry(
    school, seeded_calendar, klass, kids, teacher, supervisor
):
    periods = _periods(school, klass, teacher, 3)
    _confirm(klass, periods[0], {kids[0]: "absent", kids[1]: "absent"}, supervisor)
    _confirm(klass, periods[1], {kids[0]: "absent"}, supervisor)
    _confirm(klass, periods[2], {}, supervisor)

    report = daily_report(school, SUNDAY)

    flags = {r.student: r.ministry_flag for r in report.rows}
    assert flags[kids[0]] == "unexcused", "غاب الأولى والثانية"
    assert flags[kids[1]] == "", "غاب الأولى وحدَها"


def test_no_flag_on_an_incomplete_record(school, seeded_calendar, klass, kids, teacher, supervisor):
    """الثانيةُ لم تُرصد — لا يُرفع طالبٌ على رصدٍ ناقص."""
    periods = _periods(school, klass, teacher, 3)
    _confirm(klass, periods[0], {kids[0]: "absent"}, supervisor)

    (row,) = daily_report(school, SUNDAY).rows

    assert row.ministry_flag == ""
    assert row.unrecorded_periods == 2


def test_an_excused_absence_is_flagged_excused(
    school, seeded_calendar, klass, kids, teacher, supervisor
):
    from operations.models import StudentAttendance

    periods = _periods(school, klass, teacher, 2)
    for session in periods:
        _confirm(klass, session, {kids[0]: "absent"}, supervisor)
    StudentAttendance.objects.filter(student=kids[0]).update(excuse_type="medical")

    (row,) = daily_report(school, SUNDAY).rows

    assert row.ministry_flag == "excused"
    assert row.ministry_label == "غائب بعذر"
    assert [s.letter for s in row.slots] == ["ع", "ع"]


def test_the_page_lists_students_once_and_names_the_ministry_rows(
    client_as, school, seeded_calendar, klass, kids, teacher, supervisor
):
    for session in _periods(school, klass, teacher, 2):
        _confirm(klass, session, {kids[0]: "absent"}, supervisor)

    body = (
        client_as(supervisor)
        .get(reverse("daily_report") + f"?date={SUNDAY.isoformat()}")
        .content.decode()
    )

    assert body.count("طالب 0") == 2, "في الجدول وفي قائمة الرفع الوزاريّ"
    assert "غائب بلا عذر" in body
    assert "طالب 1" not in body, "من لم يغب ولم يتأخّر لا يُدرج"

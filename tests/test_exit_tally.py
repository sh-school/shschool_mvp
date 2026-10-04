"""[W-20261004-018] عدّادُ الخروج المرحَّل والحفظُ اليوميّ — أمرُ المالك 2026-10-04.

الخروجُ الذي لم يعد صاحبُه بنهاية حصّته يمتدّ بسطرٍ `continued_from` في الحصّة التالية حتى آخر حصّةٍ في اليوم؛ والملخّصُ اليوميّ
`DailyExitTally` (عددٌ ومجموعُ مدّة) يُعاد حسابُه من `ClassExit` فلا يتضاعف بالتكرار؛ واليومُ التالي من الصفر.
"""

import datetime as dt

import pytest
from django.urls import reverse
from django.utils import timezone

from operations.class_exit import (
    carry_over,
    close_for_absence,
    close_unreturned,
    come_back,
    leave,
    tally_of,
)
from operations.models import AttendanceEntry, ClassExit, DailyExitTally, Session
from tests.attendance_fixtures import *  # noqa: F401,F403
from tests.attendance_fixtures import MONDAY, SUNDAY, at

pytestmark = pytest.mark.django_db


@pytest.fixture
def day(school, klass, teacher, session, bells):
    """يومُ الأحد بثلاث حصص: 7:10 (هي `session`) و8:00 و12:45 — آخرُها يُنهي الدوام 13:30."""
    second = Session.objects.create(
        school=school,
        class_group=klass,
        teacher=teacher,
        date=SUNDAY,
        start_time=dt.time(8, 0),
        end_time=dt.time(8, 45),
        status="scheduled",
    )
    third = Session.objects.create(
        school=school,
        class_group=klass,
        teacher=teacher,
        date=SUNDAY,
        start_time=dt.time(12, 45),
        end_time=dt.time(13, 30),
        status="scheduled",
    )
    return [session, second, third]


def test_an_exit_without_return_is_carried_into_the_next_periods_until_the_last_one(kid, day):
    first, second, third = day
    origin = leave(first, kid, "restroom", by=first.teacher, now=at(7, 30))
    close_unreturned(first, now=at(7, 56))
    carried = ClassExit.objects.get(session=second, student=kid)
    assert carried.continued_from_id == origin.id
    assert carried.session_id == second.id  # يحتفظ بحصّته ليُستخرج تفصيلُ الحصّة والمادّة
    assert carried.left_at == at(7, 55) and carried.returned_at is None

    close_unreturned(second, now=at(8, 46))
    assert ClassExit.objects.get(session=third, student=kid).continued_from_id == carried.id

    close_unreturned(third, now=at(13, 31))  # آخرُ حصّةٍ: يُغلق ولا امتدادَ بعدها
    last = ClassExit.objects.get(session=third, student=kid)
    assert last.returned_at == at(13, 30)
    assert ClassExit.objects.filter(student=kid).count() == 3


def test_three_exits_in_a_day_count_three_and_the_carried_parts_do_not_add_a_count(kid, day):
    first, second, third = day
    for start, back, session in (
        (at(7, 15), at(7, 20), first),
        (at(7, 30), None, first),  # يمتدّ إلى الحصّة الثانية
        (at(12, 50), at(13, 0), third),
    ):
        leave(session, kid, "restroom", by=session.teacher, now=start)
        if back:
            come_back(session, kid, now=back)
    close_unreturned(first, now=at(7, 56))
    come_back(second, kid, now=at(8, 10))
    tally = DailyExitTally.objects.get(student=kid, date=SUNDAY)
    assert tally.exit_count == 3  # الامتدادُ مدّةٌ لا مرّةٌ رابعة
    # 5 د + (7:30→7:55 = 25 د) + (7:55→8:10 = 15 د) + 10 د
    assert tally.total_seconds == (5 + 25 + 15 + 10) * 60


def test_the_open_exit_is_counted_up_to_the_query_moment_not_ignored(kid, day):
    first = day[0]
    leave(first, kid, "clinic", by=first.teacher, now=at(7, 20))
    count, seconds = tally_of(kid, SUNDAY, now=at(7, 50))
    assert (count, seconds) == (1, 30 * 60)  # الأجزاءُ المغلقة (لا شيء) + المفتوحُ حتى لحظة الاستعلام


def test_a_new_day_starts_from_zero(kid, klass, teacher, day):
    first = day[0]
    leave(first, kid, "restroom", by=teacher, now=at(7, 20))
    come_back(first, kid, now=at(7, 25))
    assert tally_of(kid, SUNDAY, now=at(9, 0)) == (1, 300)
    assert tally_of(kid, MONDAY, now=at(9, 0, day=MONDAY)) == (0, 0)


def test_the_tally_refresh_is_idempotent(kid, day):
    first = day[0]
    leave(first, kid, "restroom", by=first.teacher, now=at(7, 20))
    for _ in range(3):
        come_back(first, kid, now=at(7, 25))
        close_unreturned(first, now=at(7, 56))
    tally = DailyExitTally.objects.get(student=kid, date=SUNDAY)
    assert (tally.exit_count, tally.total_seconds) == (1, 300)
    assert DailyExitTally.objects.filter(student=kid).count() == 1


def test_carrying_twice_does_not_duplicate_the_continuation(kid, day):
    first, second, _ = day
    leave(first, kid, "restroom", by=first.teacher, now=at(7, 30))
    close_unreturned(first, now=at(7, 56))
    assert carry_over(second, now=at(8, 1)) == 0
    assert ClassExit.objects.filter(session=second, student=kid).count() == 1


def test_a_student_marked_absent_gets_no_exit_and_marking_absent_closes_an_open_one(
    client_as, kid, day, teacher
):
    first = day[0]
    leave(first, kid, "restroom", by=teacher, now=at(7, 20))
    assert close_for_absence(first, kid, now=at(7, 25)).returned_at == at(7, 25)
    AttendanceEntry.objects.create(
        school=first.school, session=first, student=kid, status="absent", entered_by=teacher
    )
    assert leave(first, kid, "clinic", by=teacher, now=at(7, 30)) is None  # الغائبُ لا يُفتح له خروج
    assert ClassExit.objects.filter(student=kid).count() == 1


def test_a_late_tap_keeps_the_entry_moment_and_computes_minutes_from_the_period_start(
    client_as, kid, day, teacher, monkeypatch
):
    first = day[0]
    monkeypatch.setattr(timezone, "now", lambda: at(7, 25))
    response = client_as(teacher).post(
        reverse("attendance_entry", args=[first.id]),
        {"student_id": str(kid.id), "status": "late", "tapped_at": str(int(at(7, 25).timestamp()))},
    )
    assert response.status_code in (200, 204)
    entry = AttendanceEntry.objects.get(session=first, student=kid)
    assert entry.status == "late"
    assert entry.tardiness_minutes == 15  # 7:10 → 7:25 آلياً

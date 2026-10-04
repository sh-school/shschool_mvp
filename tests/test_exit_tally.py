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
    exit_day_summary,
    leave,
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
    assert (
        origin.destination == carried.destination == "restroom"
    )  # الوجهةُ محفوظةٌ في السطر الأصل وتمتدّ مع الامتداد
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
    summary = exit_day_summary(kid, SUNDAY, now=at(7, 50))
    assert (summary.count, summary.seconds) == (
        1,
        30 * 60,
    )  # الأجزاءُ المغلقة (لا شيء) + المفتوحُ حتى لحظة الاستعلام


def test_a_new_day_starts_from_zero(kid, klass, teacher, day):
    first = day[0]
    leave(first, kid, "restroom", by=teacher, now=at(7, 20))
    come_back(first, kid, now=at(7, 25))
    today = exit_day_summary(kid, SUNDAY, now=at(9, 0))
    assert (today.count, today.seconds) == (1, 300)
    other = exit_day_summary(kid, MONDAY, now=at(9, 0, day=MONDAY))
    assert (other.count, other.seconds) == (0, 0)


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


def test_the_summary_is_cut_at_the_end_of_the_students_day_and_the_background_job_flags_him(
    kid, day
):
    """نهايةُ الدوام آخرُ حصّةٍ مجدولةٍ للطالب (13:30): لا يتضخّم المجموعُ بعدها، وتُغلقه المهمّةُ الخلفيّة بعلامةٍ صريحة لا صامتاً."""
    first, second, third = day
    leave(third, kid, "clinic", by=third.teacher, now=at(12, 50))
    late_evening = exit_day_summary(kid, SUNDAY, now=at(20, 0))
    assert (
        late_evening.seconds == (13 * 60 + 30 - (12 * 60 + 50)) * 60
    )  # 40 د إلى 13:30 لا إلى 20:00
    from operations.exit_reflection import reflect_period_exits
    from operations.period_register import periods_of

    period = next(p for p in periods_of(third.class_group, SUNDAY) if p.start == third.start_time)
    reflect_period_exits(third.class_group, SUNDAY, period, at(20, 0))
    flagged = ClassExit.objects.get(session=third, student=kid)
    assert flagged.system_closed is True and flagged.returned_at == at(13, 30)
    reflect_period_exits(third.class_group, SUNDAY, period, at(20, 5))  # تكرارُ المهمّة
    flagged.refresh_from_db()
    assert flagged.system_closed is True  # المؤشّرُ باقٍ بعد المهمّة الخلفيّة


def test_an_exit_carried_through_several_periods_counts_once_and_the_carry_never_adds_to_the_count(
    kid, day
):
    first, second, third = day
    leave(first, kid, "restroom", by=first.teacher, now=at(7, 30))
    close_unreturned(first, now=at(7, 56))
    close_unreturned(second, now=at(8, 46))
    assert ClassExit.objects.filter(student=kid).count() == 3  # ثلاثةُ أسطرٍ بحصصها
    assert DailyExitTally.objects.get(student=kid, date=SUNDAY).exit_count == 1


def test_the_supervisor_cannot_confirm_absent_for_a_student_who_has_a_registered_exit(
    kid, day, holder
):
    from operations.period_register import confirm_period

    first = day[0]
    leave(first, kid, "restroom", by=first.teacher, now=at(7, 30))
    result = confirm_period(
        first.class_group,
        SUNDAY,
        first.start_time,
        {str(kid.id): {"status": "absent"}},
        holder,
        now=at(7, 40),
    )
    assert result.conflicts == 1  # يُعرض تعارضاً ولا يُثبَّت
    from operations.models import StudentAttendance

    assert not StudentAttendance.objects.filter(
        session=first, student=kid, status="absent"
    ).exists()


def test_the_supervisor_sheet_shows_the_did_not_return_indicator_for_a_student_who_is_out(
    client_as, kid, day, holder, monkeypatch
):
    from django.urls import reverse
    from django.utils import timezone

    first = day[0]
    leave(first, kid, "clinic", by=first.teacher, now=at(7, 20))
    monkeypatch.setattr(timezone, "now", lambda: at(7, 40))
    body = (
        client_as(holder)
        .get(
            reverse("wings:record_section", args=[first.class_group_id]),
            {"date": SUNDAY.isoformat()},
        )
        .content.decode()
    )
    assert 'title="خرج بإذن ولم يعد حتى الآن">لم يعد<' in body


def test_the_supervisor_sees_the_conflict_warning_when_absent_is_refused_over_an_exit(
    client_as, kid, day, holder, monkeypatch
):
    from django.contrib.messages import get_messages
    from django.urls import reverse
    from django.utils import timezone

    first = day[0]
    leave(first, kid, "clinic", by=first.teacher, now=at(7, 20))
    monkeypatch.setattr(timezone, "now", lambda: at(7, 40))
    response = client_as(holder).post(
        reverse("wings:record_period", args=[first.class_group_id]),
        {"date": SUNDAY.isoformat(), "start": "07:10", f"s-{kid.id}": "absent"},
    )
    assert response.status_code == 302
    texts = [str(m) for m in get_messages(response.wsgi_request)]
    assert any("تعارضٌ لم يُثبَّت: 1" in t for t in texts)


def test_the_daily_summary_keeps_the_destination_of_every_exit(kid, day):
    """أمرُ المالك: الوجهةُ (العيادة/الإدارة/دورة المياه) تُحفظ أيضاً في الملخّص اليوميّ، ويبقى المفتوحُ منسوباً لوجهته."""
    first = day[0]
    leave(first, kid, "clinic", by=first.teacher, now=at(7, 12))
    come_back(first, kid, now=at(7, 22))
    leave(first, kid, "restroom", by=first.teacher, now=at(7, 30))
    come_back(first, kid, now=at(7, 35))
    leave(first, kid, "admin", by=first.teacher, now=at(7, 40))
    row = DailyExitTally.objects.get(student=kid, date=SUNDAY)
    assert row.by_destination["clinic"] == {"count": 1, "seconds": 600}
    assert row.by_destination["restroom"] == {"count": 1, "seconds": 300}
    summary = exit_day_summary(kid, SUNDAY, now=at(7, 50))
    assert summary.by_destination["admin"]["seconds"] == 600  # المفتوحُ يُحتسب إلى لحظة الاستعلام
    assert [part[3] for part in summary.parts] == ["clinic", "restroom", "admin"]


def test_the_exit_tables_are_visible_in_the_django_admin(client, db):
    from django.contrib import admin

    from operations.models import ClassExit, DailyExitTally

    assert ClassExit in admin.site._registry
    assert DailyExitTally in admin.site._registry


def test_the_saved_late_minutes_stay_visible_on_the_teacher_card_after_reload(
    client_as, kid, day, teacher, monkeypatch
):
    from django.urls import reverse
    from django.utils import timezone

    first = day[0]
    monkeypatch.setattr(timezone, "now", lambda: at(7, 25))
    client_as(teacher).post(
        reverse("attendance_entry", args=[first.id]),
        {"student_id": str(kid.id), "status": "late", "tapped_at": str(int(at(7, 25).timestamp()))},
    )
    body = client_as(teacher).get(reverse("attendance", args=[first.id])).content.decode()
    assert 'title="دقائقُ التأخّر محسوبةٌ من بدء الحصّة">15 د<' in body

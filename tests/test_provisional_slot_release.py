"""hotfix W-20261006-001: مؤقّتةٌ **غيرُ مرصودةٍ** تحجز الخانةَ تُحرَّر (cancelled + period_number=NULL) بدل رفض معلّمٍ آخر؛ والمرصودةُ تُرفض باسم الشعبة؛ والحقيقيّةُ لا تُمسّ."""

import datetime as dt
from unittest.mock import patch

import pytest
from django.db import IntegrityError
from django.utils import timezone

from core.models import AuditLog
from operations.models import AttendanceEntry, Session, StudentAttendance, SubjectClassAssignment
from operations.services import provisional_session as provisional
from tests.attendance_fixtures import *  # noqa: F401,F403
from tests.attendance_fixtures import SUNDAY, _staff
from tests.test_provisional_session import (  # noqa: F401
    _flag_on_and_today_is_sunday,
    assigned,
    subject,
)

pytestmark = pytest.mark.django_db


def _assign(school, year, klass, subject, teacher):
    SubjectClassAssignment.objects.create(
        school=school,
        class_group=klass,
        subject=subject,
        teacher=teacher,
        weekly_periods=2,
        academic_year=year,
    )


@pytest.fixture
def rival(school, year, assigned, subject):
    """معلّمٌ ثانٍ مُسنَدةٌ إليه الشعبةُ نفسُها (يجرّب حصصاً فيحجزها)."""
    other = _staff(school, "teacher", "معلّمٌ مجرِّب", "29000001055")
    _assign(school, year, assigned, subject, other)
    return other


def _aged(session, minutes):
    Session.objects.filter(pk=session.pk).update(
        created_at=timezone.now() - dt.timedelta(minutes=minutes)
    )


def test_a_fresh_unmarked_session_is_not_released_so_its_owner_keeps_filling_it(
    school, assigned, teacher, rival
):
    owner, _ = provisional.create(rival, school, assigned.id, 3)
    _aged(owner, 2)  # أُنشئت قبل دقيقتين: صاحبُها يملأ الكشفَ الآن

    with pytest.raises(provisional.ProvisionalRefusedError) as refusal:
        provisional.create(teacher, school, assigned.id, 3)

    owner.refresh_from_db()
    assert owner.status != "cancelled" and owner.period_number == 3
    assert assigned.short_label in str(refusal.value) and "الحصّة 3" in str(refusal.value)


def test_an_unmarked_provisional_of_another_teacher_is_released_not_refused(
    school, assigned, teacher, rival
):
    squatter, _ = provisional.create(rival, school, assigned.id, 1)
    _aged(squatter, 30)

    mine, created = provisional.create(teacher, school, assigned.id, 1)

    squatter.refresh_from_db()
    assert created is True and mine.pk != squatter.pk
    assert Session.objects.filter(pk=squatter.pk).exists(), "لا حذف"
    assert squatter.status == "cancelled" and squatter.period_number is None
    audit = AuditLog.objects.get(object_id=str(squatter.pk), object_repr__contains="تحريرُ")
    assert audit.changes["reason"] == "slot_released_unmarked"
    assert "national_id" not in str(audit.changes)


def test_the_same_teachers_unmarked_session_in_another_class_is_released(
    school, year, wing, band, assigned, teacher, subject
):
    from tests.conftest import ClassGroupFactory

    other = ClassGroupFactory(
        school=school, grade="G7", section="2", level_type="prep", academic_year=year, wing=wing
    )
    type(other).objects.filter(pk=other.pk).update(time_band=band)
    _assign(school, year, other, subject, teacher)
    wrong, _ = provisional.create(teacher, school, other.id, 2)  # الشعبةُ الخطأ
    _aged(wrong, 30)

    right, created = provisional.create(teacher, school, assigned.id, 2)

    wrong.refresh_from_db()
    assert created and wrong.status == "cancelled" and wrong.period_number is None
    assert right.class_group == assigned and right.period_number == 2


@pytest.mark.parametrize("kind", ["entry", "attendance"])
def test_a_marked_blocker_is_refused_naming_the_class_and_period(
    school, assigned, teacher, rival, kid, kind
):
    squatter, _ = provisional.create(rival, school, assigned.id, 1)
    if kind == "attendance":
        StudentAttendance.objects.create(
            session=squatter, student=kid, school=school, status="absent", source="teacher"
        )
    else:
        AttendanceEntry.objects.create(
            school=school, session=squatter, student=kid, status="absent", entered_by=rival
        )

    with pytest.raises(provisional.ProvisionalRefusedError) as refusal:
        provisional.create(teacher, school, assigned.id, 1)

    message = str(refusal.value)
    assert assigned.short_label in message and "الحصّة 1" in message and "رصد" in message
    squatter.refresh_from_db()
    assert squatter.status != "cancelled" and squatter.period_number == 1, "المرصودةُ لا تُمسّ"


def test_a_lost_race_on_the_constraint_is_refused_by_meaning_not_500(school, assigned, teacher):
    with patch.object(Session.objects, "create", side_effect=IntegrityError("uniq")):
        with pytest.raises(provisional.ProvisionalRefusedError) as refusal:
            provisional.create(teacher, school, assigned.id, 3)

    assert "الحصّة 3" in str(refusal.value) and "سبقتْه" not in str(refusal.value)


def test_released_slots_do_not_count_against_the_daily_cap(school, assigned, teacher):
    for number in (1, 2, 3):
        session, _ = provisional.create(teacher, school, assigned.id, number)
        Session.objects.filter(pk=session.pk).update(status="cancelled", period_number=None)

    again, created = provisional.create(teacher, school, assigned.id, 1)

    assert created and again.period_number == 1


def test_real_sessions_are_never_touched(school, assigned, teacher, rival, subject):
    real = Session.objects.create(
        school=school,
        class_group=assigned,
        teacher=rival,
        subject=subject,
        date=SUNDAY,
        start_time=dt.time(7, 10),
        end_time=dt.time(7, 55),
        status="scheduled",
    )

    mine, created = provisional.create(teacher, school, assigned.id, 1)

    real.refresh_from_db()
    assert created and real.status == "scheduled" and real.provisional is False
    assert mine.provisional_until > timezone.now()

"""مصالحةُ الجلسات مع الجدول بعد الاعتماد.

جلساتُ الأسبوع الأوّل من 2026-2027 وُلّدت على الإنتاج من شُعب 2025-2026 قبل
اعتماد الجدول الجديد، وبقيت 845 جلسةً لعامٍ منقضٍ لأنّ التوليد لا يعيد يوماً
فيه جلسات. هنا: التوليدُ لا يَعُدّ جلساتِ عامٍ آخر، والمصالحةُ تحذف ما لا
يطابق بلا حضور وتُبقي ما مُسّ وتُنشئ الناقص.
"""

import datetime as dt
from datetime import date

import pytest

from core.models import ClassGroup
from operations.models import ScheduleSlot, Session, StudentAttendance, Subject
from operations.services import ScheduleService
from tests.conftest import MembershipFactory, RoleFactory, UserFactory

SUNDAY = date(2026, 3, 22)


def _teacher(school, name):
    t = UserFactory(full_name=name)
    MembershipFactory(user=t, school=school, role=RoleFactory(school=school, name="teacher"))
    return t


def _slot(school, teacher, cg, subject, start=dt.time(7, 10), end=dt.time(7, 55), **extra):
    return ScheduleSlot.objects.create(
        school=school,
        teacher=teacher,
        class_group=cg,
        subject=subject,
        day_of_week=0,
        period_number=1,
        start_time=start,
        end_time=end,
        academic_year="2026-2027",
        **extra,
    )


@pytest.mark.django_db
def test_sessions_of_another_year_do_not_make_the_day_look_generated(school):
    old_cg = ClassGroup.objects.create(
        school=school, grade="G8", section="1", academic_year="2025-2026"
    )
    new_cg = ClassGroup.objects.create(
        school=school, grade="G8", section="1", academic_year="2026-2027"
    )
    t = _teacher(school, "معلّم")
    subject = Subject.objects.create(school=school, name_ar="الرياضيات")
    Session.objects.create(
        school=school,
        teacher=t,
        class_group=old_cg,
        subject=subject,
        date=SUNDAY,
        start_time=dt.time(8, 0),
        end_time=dt.time(8, 45),
        status="scheduled",
    )
    _slot(school, t, new_cg, subject)

    created = ScheduleService.ensure_sessions_for_date(school, SUNDAY, academic_year="2026-2027")

    assert created == 1, "اليومُ ليس «كاملاً» بجلسةِ عامٍ آخر"
    assert Session.objects.filter(date=SUNDAY, class_group=new_cg).count() == 1


@pytest.mark.django_db
def test_resync_replaces_stale_sessions_but_keeps_those_with_attendance(school):
    old_cg = ClassGroup.objects.create(
        school=school, grade="G8", section="1", academic_year="2025-2026"
    )
    new_cg = ClassGroup.objects.create(
        school=school, grade="G8", section="1", academic_year="2026-2027"
    )
    t_old, t_new = _teacher(school, "معلّم قديم"), _teacher(school, "معلّم جديد")
    subject = Subject.objects.create(school=school, name_ar="الرياضيات")
    stale = Session.objects.create(
        school=school,
        teacher=t_old,
        class_group=old_cg,
        subject=subject,
        date=SUNDAY,
        start_time=dt.time(8, 0),
        end_time=dt.time(8, 45),
        status="scheduled",
    )
    touched = Session.objects.create(
        school=school,
        teacher=t_old,
        class_group=old_cg,
        subject=subject,
        date=SUNDAY,
        start_time=dt.time(9, 0),
        end_time=dt.time(9, 45),
        status="scheduled",
    )
    student = UserFactory(full_name="طالب")
    StudentAttendance.objects.create(
        session=touched, student=student, school=school, status="present"
    )
    _slot(school, t_new, new_cg, subject)

    result = ScheduleService.resync_sessions_for_date(school, SUNDAY, academic_year="2026-2027")

    assert result == {"deleted": 1, "created": 1, "kept": 1}
    assert not Session.objects.filter(id=stale.id).exists()
    assert Session.objects.filter(id=touched.id).exists(), "ما سُجّل عليه حضورٌ لا يُحذف"
    assert Session.objects.filter(date=SUNDAY, class_group=new_cg, teacher=t_new).exists()


@pytest.mark.django_db
def test_resync_is_a_no_op_when_sessions_already_match(school):
    cg = ClassGroup.objects.create(
        school=school, grade="G8", section="1", academic_year="2026-2027"
    )
    t = _teacher(school, "معلّم")
    _slot(school, t, cg, Subject.objects.create(school=school, name_ar="الرياضيات"))
    ScheduleService.ensure_sessions_for_date(school, SUNDAY, academic_year="2026-2027")

    result = ScheduleService.resync_sessions_for_date(school, SUNDAY, academic_year="2026-2027")

    assert result == {"deleted": 0, "created": 0, "kept": 0}

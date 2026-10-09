"""تجهيزاتٌ مشتركة لاختبارات الغياب (فصول وطلاب ومشرف وحصص وتثبيت مباشر) — كانت في اختبارات الكشف القديم المحذوف."""

import datetime as dt

import pytest
from django.utils import timezone

from behavior.models import BehaviorInfraction
from core.academic_calendar import academic_year_for_school
from core.models import Wing
from operations.models import PeriodConfirmation, Session, StudentAttendance, Subject
from operations.period_register import sync_escapes
from tests.conftest import (
    ClassGroupFactory,
    MembershipFactory,
    RoleFactory,
    StudentEnrollmentFactory,
    UserFactory,
)

pytestmark = pytest.mark.django_db

SUNDAY = dt.date(2026, 9, 13)


def at(hour, minute, day=SUNDAY):
    return timezone.make_aware(dt.datetime.combine(day, dt.time(hour, minute)))


@pytest.fixture
def year(school):
    return academic_year_for_school(school)


@pytest.fixture
def klass(school, year):
    return ClassGroupFactory(
        school=school, grade="G7", section="1", level_type="prep", academic_year=year
    )


@pytest.fixture
def kids(school, klass):
    made = []
    for i in range(4):
        student = UserFactory(full_name=f"طالب {i}", national_id=f"2930000000{i}")
        StudentEnrollmentFactory(student=student, class_group=klass)
        made.append(student)
    return made


@pytest.fixture
def teacher(school):
    user = UserFactory(full_name="معلّم الحصّة", national_id="29300000090")
    MembershipFactory(user=user, school=school, role=RoleFactory(school=school, name="teacher"))
    return user


@pytest.fixture
def other_teacher(school):
    """معلّمٌ ثانٍ — زوجُ الاختيار معلّمان، وقيدُ `no_teacher_time_overlap` صادق."""
    user = UserFactory(full_name="معلّم الزوج الثاني", national_id="29300000092")
    MembershipFactory(user=user, school=school, role=RoleFactory(school=school, name="teacher"))
    return user


@pytest.fixture
def supervisor(school, klass, year):
    user = UserFactory(full_name="مشرف الجناح", national_id="29300000091")
    MembershipFactory(
        user=user, school=school, role=RoleFactory(school=school, name="admin_supervisor")
    )
    wing = Wing.objects.create(
        school=school, code="w1", name="جناح 1", academic_year=year, supervisor=user
    )
    klass.wing = wing
    klass.save(update_fields=["wing"])
    return user


@pytest.fixture
def subjects(school):
    return [
        Subject.objects.create(school=school, name_ar=name, code=code)
        for name, code in (("الرياضيات", "MATH"), ("العلوم", "SCI"))
    ]


def _periods(school, klass, teacher, count=7, day=SUNDAY, at_hour=7):
    """حصصُ اليوم — تبدأ :10 وتنتهي :55 من كلّ ساعة، فتُعرف نوافذُها."""
    return [
        Session.objects.create(
            school=school,
            class_group=klass,
            teacher=teacher,
            date=day,
            start_time=dt.time(at_hour + i, 10),
            end_time=dt.time(at_hour + i, 55),
            status="scheduled",
        )
        for i in range(count)
    ]


def _elective_twin(school, klass, other_teacher, day=SUNDAY, index=3):
    """خانةٌ واحدةٌ حصّتان: مادّتان ومعلّمان، كزوج الاختيار في الواقع."""
    first = Session.objects.filter(class_group=klass, date=day).order_by("start_time")[index]
    first.elective_group = "تكنولوجيا"
    first.save(update_fields=["elective_group"])
    return Session.objects.create(
        school=school,
        class_group=klass,
        teacher=other_teacher,
        date=day,
        start_time=first.start_time,
        end_time=first.end_time,
        status="scheduled",
        elective_group="فنون بصريّة",
    )


def _confirm(klass, session, marks, by, now=None, day=SUNDAY):
    """يكتب رصدَ حصّةِ `session` مباشرةً لتجهيز الاختبارات (الكشفُ القديم حُذف) — `marks` = {طالب: حالة} أو {طالب: {status, whereabouts, late_minutes}}."""
    from operations.day_attendance import SOURCE, enrolled_of

    now = now or at(23, 0, day)
    sessions = list(
        Session.objects.filter(class_group=klass, date=day, start_time=session.start_time)
    )
    tally = {"present": 0, "absent": 0, "late": 0}
    for enrollment in enrolled_of(klass):
        student = enrollment.student
        value = marks.get(student) or {}
        value = value if isinstance(value, dict) else {"status": value}
        status = value.get("status") or "present"
        tally[status] = tally.get(status, 0) + 1
        for one in sessions:
            StudentAttendance.objects.update_or_create(
                session=one,
                student=student,
                defaults={
                    "school": klass.school,
                    "status": status,
                    "source": SOURCE,
                    "marked_by": by,
                    "whereabouts": value.get("whereabouts") or "",
                    "late_minutes": value.get("late_minutes"),
                },
            )
    PeriodConfirmation.objects.get_or_create(
        class_group=klass,
        date=day,
        start_time=session.start_time,
        defaults={
            "school": klass.school,
            "end_time": session.end_time,
            "confirmed_by": by,
            "first_confirmed_at": now,
            "present_count": tally["present"],
            "absent_count": tally["absent"],
            "late_count": tally["late"],
        },
    )
    sync_escapes(klass, day, by)


def _auto(student, rule):
    return BehaviorInfraction.objects.filter(student=student, auto_rule=rule)

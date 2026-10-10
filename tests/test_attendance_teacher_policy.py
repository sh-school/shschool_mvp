"""[LEGAL] سياسةُ رصد المعلّم الفعليّ واعتمادِه — من يُدخل، ومتى، ومن يعتمد (W-20261002-020).

قراراتُ المالك التي تحرسها هذه الاختبارات (D-125م وD-126م وD-128م وD-129م):
- المعلّمُ الفعليّ للحصّة (`Session.teacher`) يُدخل رصداً **مبدئيّاً** لطلبة حصّته وحدَهم، من بدء
  الحصّة حتّى نهاية اليوم الدراسيّ (بإعداد جرس المدرسة، والتاريخُ بتوقيت الدوحة لا UTC).
- يعتمده **حاملُ جناح الشعبة يومَ الحصّة** (من `WingCoverage`)، والقيادةُ حين لا حاملَ فقط؛
  لا المعلّمُ ولا من أدخل، ولا المطوّرُ ولو كان superuser.
- التربيةُ الخاصّة (شعبةٌ بلا جناح): رصدُ معلّمها نهائيٌّ بلا اعتماد.

هذه اختباراتُ السياسة وحدَها (دوالُّ بلا تخزين)؛ والتخزينُ والسجلُّ في `test_attendance_entries.py`.
الرموزُ E/S/A/G/X من مواصفة W-020.
"""

import datetime as dt

import pytest

from core.models import TimeBand
from core.models.academic import WingCoverage  # noqa: F401
from operations.attendance_policy import (
    can_enter,
    school_day_end,
)
from operations.models import Session, TimeSlotConfig
from tests.attendance_fixtures import *  # noqa: F401,F403
from tests.attendance_fixtures import (
    ENROLLED,
    MONDAY,
    SATURDAY,
    SUNDAY,
    _staff,
    at,
)
from tests.conftest import (
    ClassGroupFactory,
    SchoolFactory,
    StudentEnrollmentFactory,
    UserFactory,
)

pytestmark = pytest.mark.django_db


# ══════════════════════════════════════════════════════════════════
# نهايةُ اليوم الدراسيّ — دالّةٌ واحدةٌ باسمٍ صريح، تُختبر عند الحدّ
# ══════════════════════════════════════════════════════════════════


def test_school_day_end_is_the_last_slot_of_the_bell(school, bells):
    assert school_day_end(school, SUNDAY) == dt.time(13, 30)


def test_school_day_end_is_none_when_no_bell_is_configured(school):
    assert school_day_end(school, SUNDAY) is None


def test_school_day_end_is_none_on_a_day_without_school(school, bells):
    assert school_day_end(school, SATURDAY) is None


def test_school_day_end_follows_the_band_when_given(school, bells):
    other = TimeBand.objects.create(school=school, code="ninth", name="تاسع", floor="first")
    TimeSlotConfig.objects.create(
        school=school,
        band=other,
        day_type="regular",
        period_number=1,
        start_time=dt.time(7, 10),
        end_time=dt.time(12, 0),
    )
    assert school_day_end(school, SUNDAY, band=other) == dt.time(12, 0)
    assert school_day_end(school, SUNDAY) == dt.time(13, 30)


# ══════════════════════════════════════════════════════════════════
# E — الإدخال
# ══════════════════════════════════════════════════════════════════


def test_e1_the_teacher_of_the_session_may_enter_inside_the_window(session, teacher, kid):
    verdict = can_enter(teacher, session, kid, now=at(7, 30))
    assert verdict.allowed, verdict.reason


def test_e2_another_teacher_may_not_enter(session, other_teacher, kid):
    verdict = can_enter(other_teacher, session, kid, now=at(7, 30))
    assert not verdict.allowed
    assert verdict.reason == "not_teacher"


def test_e3_a_student_of_another_section_is_refused(school, year, session, teacher):
    """IDOR: معلّمُ الحصّة لا يرصد طالباً من شعبةٍ أخرى بتبديل المعرّف."""
    other_klass = ClassGroupFactory(
        school=school, grade="G7", section="2", level_type="prep", academic_year=year
    )
    outsider = UserFactory(full_name="طالبٌ من شعبةٍ أخرى", national_id="29000001002")
    StudentEnrollmentFactory(student=outsider, class_group=other_klass, enrolled_at=ENROLLED)
    verdict = can_enter(teacher, session, outsider, now=at(7, 30))
    assert not verdict.allowed
    assert verdict.reason == "not_enrolled"


def test_e4a_before_the_session_starts_is_refused(session, teacher, kid):
    verdict = can_enter(teacher, session, kid, now=at(7, 9, 59))
    assert not verdict.allowed
    assert verdict.reason == "before_start"


def test_e4b_exactly_at_the_start_is_accepted(session, teacher, kid):
    assert can_enter(teacher, session, kid, now=at(7, 10)).allowed


def test_e4c_the_last_moment_of_the_school_day_is_accepted(session, teacher, kid):
    assert can_enter(teacher, session, kid, now=at(13, 30)).allowed


def test_e4c_a_second_after_the_school_day_ends_is_refused(session, teacher, kid):
    verdict = can_enter(teacher, session, kid, now=at(13, 30, 1))
    assert not verdict.allowed
    assert verdict.reason == "after_window"


def test_e4d_the_next_day_is_refused(session, teacher, kid):
    verdict = can_enter(teacher, session, kid, now=at(7, 30, day=MONDAY))
    assert not verdict.allowed


def test_e4e_the_date_is_doha_not_utc(session, teacher, kid):
    """21:30 UTC من الأحد = 00:30 من الاثنين بتوقيت الدوحة: مرفوضٌ. ومن قارن بتاريخ UTC قَبِل."""
    now_utc = dt.datetime(2026, 9, 13, 21, 30, tzinfo=dt.UTC)
    assert now_utc.date() == SUNDAY
    verdict = can_enter(teacher, session, kid, now=now_utc)
    assert not verdict.allowed


def test_e4_without_a_configured_bell_the_window_is_the_session_itself(school, klass, teacher, kid):
    """لا جرسَ مضبوطاً: الأضيقُ لا ثابتٌ مخترَع — نهايةُ الحصّة نفسِها."""
    lone = Session.objects.create(
        school=school,
        class_group=klass,
        teacher=teacher,
        date=SUNDAY,
        start_time=dt.time(9, 0),
        end_time=dt.time(9, 45),
        status="scheduled",
    )
    assert can_enter(teacher, lone, kid, now=at(9, 45)).allowed
    assert not can_enter(teacher, lone, kid, now=at(9, 46)).allowed


def test_e5_a_cancelled_session_is_refused(session, teacher, kid):
    session.status = "cancelled"
    session.save(update_fields=["status"])
    verdict = can_enter(teacher, session, kid, now=at(7, 30))
    assert not verdict.allowed
    assert verdict.reason == "cancelled"


def test_e6_an_inactive_enrollment_is_refused(session, teacher, kid, klass):
    klass.enrollments.filter(student=kid).update(is_active=False)
    verdict = can_enter(teacher, session, kid, now=at(7, 30))
    assert not verdict.allowed
    assert verdict.reason == "not_enrolled"


def test_e7_a_teacher_of_another_school_is_refused(session, kid):
    foreign_school = SchoolFactory()
    foreigner = _staff(foreign_school, "teacher", "معلّمٌ من مدرسةٍ أخرى", "29000001099")
    verdict = can_enter(foreigner, session, kid, now=at(7, 30))
    assert not verdict.allowed


# ══════════════════════════════════════════════════════════════════
# S — التبديل والتغطية: الوارثُ هو `Session.teacher` وحدَه
# ══════════════════════════════════════════════════════════════════


def test_s1_the_new_teacher_of_the_session_may_enter(session, other_teacher, kid):
    session.teacher = other_teacher
    session.save(update_fields=["teacher"])
    assert can_enter(other_teacher, session, kid, now=at(7, 30)).allowed


def test_s2_the_original_teacher_loses_the_right_on_that_session(
    session, teacher, other_teacher, kid
):
    session.original_teacher = teacher
    session.teacher = other_teacher
    session.save(update_fields=["teacher", "original_teacher"])
    verdict = can_enter(teacher, session, kid, now=at(7, 30))
    assert not verdict.allowed
    assert verdict.reason == "not_teacher"


# ══════════════════════════════════════════════════════════════════
# G — أدوارٌ عابرة
# ══════════════════════════════════════════════════════════════════


def test_g1a_the_developer_may_not_enter_even_as_the_session_teacher(school, session, kid):
    developer = _staff(school, "platform_developer", "المطوّر", "29000001030")
    session.teacher = developer
    session.save(update_fields=["teacher"])
    verdict = can_enter(developer, session, kid, now=at(7, 30))
    assert not verdict.allowed
    assert verdict.reason == "developer"


def test_g2_a_superuser_who_is_not_the_teacher_may_not_enter(school, session, kid):
    root = UserFactory(full_name="superuser", national_id="29000001032", is_superuser=True)
    verdict = can_enter(root, session, kid, now=at(7, 30))
    assert not verdict.allowed


# ══════════════════════════════════════════════════════════════════
# A — الاعتماد
# ══════════════════════════════════════════════════════════════════


# ══════════════════════════════════════════════════════════════════
# X — التربيةُ الخاصّة: نهائيٌّ بلا اعتماد
# ══════════════════════════════════════════════════════════════════


def test_x1a_a_teacher_of_a_section_without_a_wing_enters_for_his_student(
    school, teacher, special_klass, bells
):
    student = UserFactory(full_name="طالب التربية الخاصّة", national_id="29000001060")
    StudentEnrollmentFactory(student=student, class_group=special_klass, enrolled_at=ENROLLED)
    sess = Session.objects.create(
        school=school,
        class_group=special_klass,
        teacher=teacher,
        date=SUNDAY,
        start_time=dt.time(8, 0),
        end_time=dt.time(8, 45),
        status="scheduled",
    )
    assert can_enter(teacher, sess, student, now=at(8, 10)).allowed


def test_e6_an_enrollment_that_began_after_the_session_date_is_refused(session, teacher, klass):
    """القيدُ بتاريخ الحصّة لا باليوم: طالبٌ قُيّد بعد الحصّة لا تُرصد له."""
    latecomer = UserFactory(full_name="طالبٌ قُيّد لاحقاً", national_id="29000001003")
    StudentEnrollmentFactory(student=latecomer, class_group=klass, enrolled_at=MONDAY)
    verdict = can_enter(teacher, session, latecomer, now=at(7, 30))
    assert not verdict.allowed
    assert verdict.reason == "not_enrolled"

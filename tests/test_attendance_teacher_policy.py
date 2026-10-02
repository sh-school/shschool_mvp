"""[LEGAL] سياسةُ رصد المعلّم الفعليّ واعتمادِه — من يُدخل، ومتى، ومن يعتمد (W-20261002-020).

قراراتُ المالك التي تحرسها هذه الاختبارات (D-125م وD-126م وD-128م وD-129م):
- المعلّمُ الفعليّ للحصّة (`Session.teacher`) يُدخل رصداً **مبدئيّاً** لطلبة حصّته وحدَهم، من بدء
  الحصّة حتّى نهاية اليوم الدراسيّ (بإعداد جرس المدرسة، والتاريخُ بتوقيت الدوحة لا UTC).
- يعتمده **حاملُ جناح الشعبة يومَ الحصّة** (من `WingCoverage`)، والقيادةُ حين لا حاملَ فقط؛
  لا المعلّمُ ولا من أدخل، ولا المطوّرُ ولو كان superuser.
- التربيةُ الخاصّة (شعبةٌ بلا جناح): رصدُ معلّمها نهائيٌّ بلا اعتماد.

هذه اختباراتُ السياسة وحدَها (دوالُّ بلا تخزين)؛ والتخزينُ والسجلُّ في ملفٍّ آخر.
الرموزُ E/S/A/G/X من مواصفة W-020.
"""

import datetime as dt

import pytest
from django.utils import timezone

from core.academic_calendar import academic_year_for_school
from core.models import TimeBand, Wing
from core.models.academic import WingCoverage
from operations.attendance_policy import (
    approval_holder,
    can_approve,
    can_enter,
    needs_approval,
    school_day_end,
)
from operations.models import Session, TimeSlotConfig
from tests.conftest import (
    ClassGroupFactory,
    MembershipFactory,
    RoleFactory,
    SchoolFactory,
    StudentEnrollmentFactory,
    UserFactory,
)

pytestmark = pytest.mark.django_db

SUNDAY = dt.date(2026, 9, 13)
MONDAY = dt.date(2026, 9, 14)
SATURDAY = dt.date(2026, 9, 12)
ENROLLED = dt.date(2026, 9, 1)


def at(hour, minute, second=0, day=SUNDAY):
    return timezone.make_aware(dt.datetime.combine(day, dt.time(hour, minute, second)))


def _staff(school, role, name, national_id):
    user = UserFactory(full_name=name, national_id=national_id)
    MembershipFactory(user=user, school=school, role=RoleFactory(school=school, name=role))
    return user


@pytest.fixture
def year(school):
    return academic_year_for_school(school)


@pytest.fixture
def band(school):
    return TimeBand.objects.create(school=school, code="ground", name="الأرضيّ", floor="ground")


@pytest.fixture
def bells(school, band):
    """جرسُ الأحد: حصّتان ثمّ فسحةٌ ثمّ حصّةٌ — **آخرُ الدوام 13:30** (لا ثابتَ في الكود)."""
    for number, start, end, brk in (
        (1, dt.time(7, 10), dt.time(7, 55), False),
        (2, dt.time(8, 0), dt.time(8, 45), False),
        (3, dt.time(12, 45), dt.time(13, 30), False),
    ):
        TimeSlotConfig.objects.create(
            school=school,
            band=band,
            day_type="regular",
            period_number=number,
            start_time=start,
            end_time=end,
            is_break=brk,
        )
    return band


@pytest.fixture
def wing(school, year, holder):
    return Wing.objects.create(
        school=school, code="w1", name="جناح 1", academic_year=year, supervisor=holder
    )


@pytest.fixture
def klass(school, year, wing, band):
    return ClassGroupFactory(
        school=school, grade="G7", section="1", level_type="prep", academic_year=year, wing=wing
    )


@pytest.fixture
def special_klass(school, year):
    """شعبةُ تربيةٍ خاصّة: بلا جناح عمداً (D-126م)."""
    return ClassGroupFactory(
        school=school,
        grade="G7",
        section="07/ESE",
        level_type="prep",
        academic_year=year,
        wing=None,
    )


@pytest.fixture
def kid(school, klass):
    student = UserFactory(full_name="طالب الشعبة", national_id="29000001001")
    StudentEnrollmentFactory(student=student, class_group=klass, enrolled_at=ENROLLED)
    return student


@pytest.fixture
def teacher(school):
    return _staff(school, "teacher", "معلّم الحصّة", "29000001010")


@pytest.fixture
def other_teacher(school):
    return _staff(school, "teacher", "معلّم آخر", "29000001011")


@pytest.fixture
def holder(school):
    return _staff(school, "admin_supervisor", "حاملُ الجناح", "29000001020")


@pytest.fixture
def session(school, klass, teacher, bells):
    return Session.objects.create(
        school=school,
        class_group=klass,
        teacher=teacher,
        date=SUNDAY,
        start_time=dt.time(7, 10),
        end_time=dt.time(7, 55),
        status="scheduled",
    )


def _cover(wing, substitute, start, end, by):
    return WingCoverage.objects.create(
        wing=wing, substitute=substitute, start_date=start, end_date=end, assigned_by=by
    )


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


def test_g1b_the_developer_may_not_approve_even_as_a_superuser_holder(
    school, wing, session, teacher
):
    developer = _staff(school, "platform_developer", "المطوّر", "29000001031")
    developer.is_superuser = True
    developer.save(update_fields=["is_superuser"])
    wing.supervisor = developer
    wing.save(update_fields=["supervisor"])
    verdict = can_approve(developer, session, entered_by=teacher)
    assert not verdict.allowed
    assert verdict.reason == "developer"


def test_g2_a_superuser_who_is_not_the_teacher_may_not_enter(school, session, kid):
    root = UserFactory(full_name="superuser", national_id="29000001032", is_superuser=True)
    verdict = can_enter(root, session, kid, now=at(7, 30))
    assert not verdict.allowed


def test_g2_a_superuser_with_no_role_may_not_approve(session, teacher):
    root = UserFactory(full_name="superuser", national_id="29000001033", is_superuser=True)
    assert not can_approve(root, session, entered_by=teacher).allowed


def test_g3_a_student_may_not_enter_nor_approve(school, session, kid, teacher):
    assert not can_enter(kid, session, kid, now=at(7, 30)).allowed
    assert not can_approve(kid, session, entered_by=teacher).allowed


def test_g3_a_parent_may_not_enter_nor_approve(school, session, kid, teacher):
    parent = _staff(school, "parent", "وليّ أمر", "29000001034")
    assert not can_enter(parent, session, kid, now=at(7, 30)).allowed
    assert not can_approve(parent, session, entered_by=teacher).allowed


# ══════════════════════════════════════════════════════════════════
# A — الاعتماد
# ══════════════════════════════════════════════════════════════════


def test_a1_the_holder_of_the_section_wing_approves(session, holder, teacher):
    verdict = can_approve(holder, session, entered_by=teacher)
    assert verdict.allowed, verdict.reason


def test_a2_the_holder_of_another_wing_may_not_approve(school, year, session, teacher):
    """**الأهمّ**: جناحُ الشعبة هو الحدّ — حاملُ جناحٍ آخر مرفوض."""
    other_holder = _staff(school, "admin_supervisor", "مشرفُ جناحٍ آخر", "29000001021")
    Wing.objects.create(
        school=school, code="w2", name="جناح 2", academic_year=year, supervisor=other_holder
    )
    verdict = can_approve(other_holder, session, entered_by=teacher)
    assert not verdict.allowed
    assert verdict.reason == "not_holder"


def test_a3_the_original_loses_the_right_while_a_coverage_is_in_force(
    school, wing, session, holder, teacher
):
    substitute = _staff(school, "admin_supervisor", "البديل", "29000001022")
    _cover(wing, substitute, SUNDAY, None, by=teacher)
    assert can_approve(substitute, session, entered_by=teacher).allowed
    verdict = can_approve(holder, session, entered_by=teacher)
    assert not verdict.allowed
    assert verdict.reason == "not_holder"


def test_a4_coverage_bounds_are_inclusive(school, wing, session, holder, teacher):
    substitute = _staff(school, "admin_supervisor", "البديل", "29000001022")
    # البدايةُ يومَ الحصّة: البديلُ يحمل.
    cover = _cover(wing, substitute, SUNDAY, SUNDAY + dt.timedelta(days=3), by=teacher)
    assert can_approve(substitute, session, entered_by=teacher).allowed
    # النهايةُ يومَ الحصّة: البديلُ يحمل.
    cover.start_date = SUNDAY - dt.timedelta(days=3)
    cover.end_date = SUNDAY
    cover.save()
    assert can_approve(substitute, session, entered_by=teacher).allowed
    # النهايةُ أمسِ: عاد الأصيل.
    cover.end_date = SATURDAY
    cover.save()
    assert not can_approve(substitute, session, entered_by=teacher).allowed
    assert can_approve(holder, session, entered_by=teacher).allowed
    # البدايةُ غداً: لم يبدأ البديل.
    cover.start_date = MONDAY
    cover.end_date = None
    cover.save()
    assert not can_approve(substitute, session, entered_by=teacher).allowed
    assert can_approve(holder, session, entered_by=teacher).allowed


def test_a5_the_holder_is_the_one_on_the_session_day_not_the_approval_day(
    school, wing, session, holder, teacher
):
    """حصّةُ الأحد غطّاها بديلٌ وانتهت تغطيتُه الاثنين: يعتمدها هو لا الأصيلُ العائد."""
    substitute = _staff(school, "admin_supervisor", "البديل", "29000001022")
    _cover(wing, substitute, SUNDAY, SUNDAY, by=teacher)
    assert approval_holder(session) == substitute
    assert can_approve(substitute, session, entered_by=teacher).allowed
    assert not can_approve(holder, session, entered_by=teacher).allowed


def test_a6_the_teacher_of_the_session_may_not_approve_his_own_session(
    school, wing, session, teacher
):
    """حتّى لو صار حاملَ الجناح: لا يعتمد رصدَ حصّته."""
    wing.supervisor = teacher
    wing.save(update_fields=["supervisor"])
    verdict = can_approve(teacher, session, entered_by=teacher)
    assert not verdict.allowed
    assert verdict.reason in {"own_session", "own_entry"}


def test_a6_nobody_approves_what_he_entered_himself(session, holder, teacher):
    verdict = can_approve(holder, session, entered_by=holder)
    assert not verdict.allowed
    assert verdict.reason == "own_entry"


def test_a7_leadership_may_not_approve_while_a_holder_exists(school, session, teacher):
    for role, nid in (
        ("principal", "29000001040"),
        ("vice_admin", "29000001041"),
        ("vice_academic", "29000001042"),
    ):
        leader = _staff(school, role, role, nid)
        verdict = can_approve(leader, session, entered_by=teacher)
        assert not verdict.allowed, role
        assert verdict.reason == "not_holder"


def test_a7_leadership_approves_when_no_holder_exists(school, wing, session, teacher):
    wing.supervisor = None
    wing.save(update_fields=["supervisor"])
    assert approval_holder(session) is None
    for role, nid in (
        ("principal", "29000001040"),
        ("vice_admin", "29000001041"),
        ("vice_academic", "29000001042"),
    ):
        leader = _staff(school, role, role, nid)
        verdict = can_approve(leader, session, entered_by=teacher)
        assert verdict.allowed, (role, verdict.reason)


def test_a8_roles_without_a_wing_or_coverage_may_not_approve(
    school, wing, session, teacher, holder
):
    for role, nid in (
        ("student_observer", "29000001050"),
        ("services_worker", "29000001051"),
        ("admin_supervisor", "29000001052"),
        ("coordinator", "29000001053"),
    ):
        user = _staff(school, role, role, nid)
        assert not can_approve(user, session, entered_by=teacher).allowed, role


def test_a8_a_student_observer_with_a_coverage_is_the_holder_and_approves(
    school, wing, session, teacher
):
    observer = _staff(school, "student_observer", "ملاحظ طلبة", "29000001054")
    _cover(wing, observer, SUNDAY, None, by=teacher)
    assert can_approve(observer, session, entered_by=teacher).allowed


# ══════════════════════════════════════════════════════════════════
# X — التربيةُ الخاصّة: نهائيٌّ بلا اعتماد
# ══════════════════════════════════════════════════════════════════


def test_x1_special_education_needs_no_approval(session, special_klass):
    assert needs_approval(session) is True
    session.class_group = special_klass
    assert needs_approval(session) is False


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


def test_x1_a_wingless_ordinary_section_is_not_special_education(school, year, session, teacher):
    """الفشلُ مغلقٌ: جناحٌ لم يُسند خطأً لا يجعل إدخالَ معلّمي شعبةٍ عاديّةٍ نهائيّاً بلا اعتماد."""
    stray = ClassGroupFactory(
        school=school, grade="G8", section="3", level_type="prep", academic_year=year, wing=None
    )
    session.class_group = stray
    assert needs_approval(session) is True
    leader = _staff(school, "principal", "المدير", "29000001070")
    assert approval_holder(session) is None
    assert can_approve(leader, session, entered_by=teacher).allowed


def test_x1_nobody_approves_a_final_special_education_entry(school, session, special_klass):
    """لا اعتمادَ يُطلب للنهائيّ: لا قيادةَ ولا غيرُها."""
    session.class_group = special_klass
    leader = _staff(school, "principal", "المدير", "29000001071")
    verdict = can_approve(leader, session, entered_by=session.teacher)
    assert not verdict.allowed
    assert verdict.reason == "final_entry"


def test_e6_an_enrollment_that_began_after_the_session_date_is_refused(session, teacher, klass):
    """القيدُ بتاريخ الحصّة لا باليوم: طالبٌ قُيّد بعد الحصّة لا تُرصد له."""
    latecomer = UserFactory(full_name="طالبٌ قُيّد لاحقاً", national_id="29000001003")
    StudentEnrollmentFactory(student=latecomer, class_group=klass, enrolled_at=MONDAY)
    verdict = can_enter(teacher, session, latecomer, now=at(7, 30))
    assert not verdict.allowed
    assert verdict.reason == "not_enrolled"

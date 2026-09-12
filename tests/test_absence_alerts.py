"""[LEGAL] الإنذار يتبع عتبات الوزارة — واحدٌ لكل عتبة، وقبل الوقوع.

كان التنبيه يقوم على «10٪ من أيام الدراسة» ويقول لوليّ الأمر إن ابنه «تجاوز
**العتبة القانونية**» — وهو ادّعاءٌ يصل إلى بيتٍ حقيقيّ، ولا سندَ له: نصّ
قانون التعليم الإلزامي لا يذكر نسبةً ولا عدد أيام.

وكان معه ثلاثة عيوبٍ عمليّة:

- يعدّ **حصصاً** والسياسة تعدّ **أياماً** — فرقٌ سبعة أضعاف بسبع حصصٍ في اليوم.
- تنبيهٌ واحد **للعام كلّه**: `get_or_create` بلا مفتاح عتبة، فمن تجاوز الأولى
  لم يُنذَر عند التي بعدها قطّ.
- يُعلم **بعد** الوقوع لا قبله.

فصار: إنذارٌ لكل عتبة، يسبقها بيومين، بنصٍّ يسمّي الاختبار وحدّه ومرجعه.
"""

from datetime import time, timedelta

import pytest

from operations.models import AbsenceAlert, Session, StudentAttendance, Subject
from operations.services import AttendanceService


@pytest.fixture
def subject(db, school):
    return Subject.objects.create(school=school, name_ar="العلوم", code="SCI")


@pytest.fixture
def year_window(db, school):
    from django.core.management import call_command

    from core.academic_calendar import academic_year_window

    call_command("seed_academic_calendar", school=school.code, verbosity=0)
    return academic_year_window(school)


@pytest.fixture
def student(db, school, class_group, year_window):
    from core.academic_calendar import academic_year_for_school
    from core.models import StudentEnrollment
    from tests.conftest import MembershipFactory, RoleFactory, UserFactory

    class_group.grade = "G7"
    class_group.academic_year = academic_year_for_school(school)
    class_group.save(update_fields=["grade", "academic_year"])

    role = RoleFactory(school=school, name="student")
    user = UserFactory(full_name="طالب الاختبار")
    MembershipFactory(user=user, school=school, role=role)
    StudentEnrollment.objects.create(student=user, class_group=class_group, is_active=True)
    return user


def _absent(school, class_group, teacher, subject, student, start, days):
    for offset in range(days):
        session = Session.objects.create(
            school=school,
            class_group=class_group,
            teacher=teacher,
            subject=subject,
            date=start + timedelta(days=offset),
            start_time=time(8, 0),
            end_time=time(8, 45),
            status="scheduled",
        )
        StudentAttendance.objects.create(
            session=session, student=student, school=school, status="absent", excuse_type=""
        )


def _gates(student):
    return sorted(AbsenceAlert.objects.filter(student=student).values_list("gate", flat=True))


def test_nothing_is_raised_while_the_student_is_far_from_any_gate(
    db, school, class_group, teacher_user, subject, student, year_window
):
    start, _ = year_window
    # يومان: يفصلهما ثلاثةٌ عن عتبة الخمسة، والهامشُ يومان — فلا إنذار.
    _absent(school, class_group, teacher_user, subject, student, start, 2)

    AttendanceService.check_absence_threshold(student, school, on=start + timedelta(days=30))

    assert _gates(student) == []


def test_the_warning_comes_before_the_gate_not_after(
    db, school, class_group, teacher_user, subject, student, year_window
):
    """ثلاثةُ أيام: يفصله يومان عن الخامسة — فيُنذَر وهو ما زال يملك أن يتدارك."""
    start, _ = year_window
    _absent(school, class_group, teacher_user, subject, student, start, 3)

    AttendanceService.check_absence_threshold(student, school, on=start + timedelta(days=30))

    assert _gates(student) == ["s1_midterm"]


def test_each_gate_raises_its_own_alert(
    db, school, class_group, teacher_user, subject, student, year_window
):
    """كان التنبيه واحداً للعام — فمن تجاوز الأولى لم يُنذَر عند ما بعدها.

    وتسعةُ أيّامٍ بأرقام 2026 تجاوزت الخامسةَ والثامنةَ، ويفصلها يومان عن
    الحادية عشرة — فثلاثةُ إنذارات.
    """
    start, _ = year_window
    _absent(school, class_group, teacher_user, subject, student, start, 9)

    AttendanceService.check_absence_threshold(student, school, on=start + timedelta(days=30))

    assert _gates(student) == ["s1_final", "s1_midterm", "s2_midterm"]


def test_the_same_gate_is_not_raised_twice(
    db, school, class_group, teacher_user, subject, student, year_window
):
    """الدالّة تُنادى عند كل تسجيل حضور — فالتكرار يُغرق وليّ الأمر."""
    start, _ = year_window
    _absent(school, class_group, teacher_user, subject, student, start, 9)

    AttendanceService.check_absence_threshold(student, school, on=start + timedelta(days=30))
    AttendanceService.check_absence_threshold(student, school, on=start + timedelta(days=30))
    AttendanceService.check_absence_threshold(student, school, on=start + timedelta(days=30))

    assert AbsenceAlert.objects.filter(student=student).count() == 3


def test_the_message_names_the_exam_its_limit_and_its_source(
    db, school, class_group, teacher_user, subject, student, year_window
):
    """«العتبة القانونية» كانت تصل إلى بيتٍ حقيقيّ بلا سند."""
    from notifications.models import InAppNotification

    start, _ = year_window
    _absent(school, class_group, teacher_user, subject, student, start, 8)

    AttendanceService.check_absence_threshold(student, school, on=start + timedelta(days=30))
    said = " ".join(InAppNotification.objects.values_list("title", flat=True)) + " ".join(
        InAppNotification.objects.values_list("body", flat=True)
    )

    assert "العتبة القانونية" not in said, "ادّعاءٌ بلا سند"
    if said.strip():
        assert "سياسة إدارة سلوك الطلبة 2026" in said
        assert "منتصف الفصل الأول" in said


def test_an_excused_day_never_triggers_an_alert(
    db, school, class_group, teacher_user, subject, student, year_window
):
    start, _ = year_window
    for offset in range(9):
        session = Session.objects.create(
            school=school,
            class_group=class_group,
            teacher=teacher_user,
            subject=subject,
            date=start + timedelta(days=offset),
            start_time=time(8, 0),
            end_time=time(8, 45),
            status="scheduled",
        )
        StudentAttendance.objects.create(
            session=session,
            student=student,
            school=school,
            status="absent",
            excuse_type="medical",
        )

    AttendanceService.check_absence_threshold(student, school, on=start + timedelta(days=30))

    assert _gates(student) == []


def test_the_second_grade_is_covered_now(
    db, school, class_group, teacher_user, subject, student, year_window
):
    """دليلُ 2026 يقول «من الصف **الأول**» — فلم تبقَ الصفوفُ 1–3 خارجه.

    وكانت سياسةُ 2018 تبدأ من الرابع، فكان الثاني يُترك بلا إنذارٍ ولو غاب
    عشرين يوماً. ولا أثرَ لهذا في مدرستنا (7–12)، لكنّ الجدولَ صار جدولَه.
    """
    start, _ = year_window
    class_group.grade = "G2"
    class_group.save(update_fields=["grade"])
    _absent(school, class_group, teacher_user, subject, student, start, 20)

    AttendanceService.check_absence_threshold(student, school, on=start + timedelta(days=30))

    assert _gates(student) == ["s1_final", "s1_midterm", "s2_final", "s2_midterm"]


def test_a_grade_with_no_table_is_left_alone(
    db, school, class_group, teacher_user, subject, student, year_window
):
    """صفٌّ لا جدولَ له في السياسة — فلا إنذار بجدولٍ لا يخصّه."""
    start, _ = year_window
    class_group.grade = "G13"
    class_group.save(update_fields=["grade"])
    _absent(school, class_group, teacher_user, subject, student, start, 20)

    AttendanceService.check_absence_threshold(student, school, on=start + timedelta(days=30))

    assert _gates(student) == []

"""[LEGAL] عدُّ أيام التمدرس — لا الحصص.

نصّ السياسة يعدّ **أيام التمدرس**، وقاعدتنا تُسجّل الحضور **بالحصّة**. فيومُ
الطالب قد يحوي سبع حصص، وغيابُه عن حصّةٍ واحدة ليس غياب يوم.

وكانت المنصّة تخلط الوحدتين في ميزانٍ واحد: تقارن صفوف `StudentAttendance`
(حصصاً) بـ`0.10 × 190` (أياماً)، والمتغيّر اسمه `threshold_days`. فبسبعِ حصصٍ
في اليوم يصير الفارق بين الوحدتين سبعة أضعاف — ولا شيء في الشاشة يكشفه.

فالقاعدة هنا صريحة: اليوم غيابٌ بلا عذر إذا كان الطالب غائباً بلا عذرٍ في
**كل** حصصه المسجَّلة ذلك اليوم. وما دونه غيابٌ جزئيّ يُحصى منفصلاً — يُعرض
ولا يُحتسب.
"""

from datetime import date, time, timedelta

import pytest

from operations.absence_standing import standing_for
from operations.models import Session, StudentAttendance, Subject


@pytest.fixture
def subject(db, school):
    return Subject.objects.create(school=school, name_ar="العلوم", code="SCI")


@pytest.fixture
def student(db, school, class_group):
    """‏`school` خاصّيةٌ مشتقّة من العضوية لا حقلٌ يُكتب — كما `role`."""
    from tests.conftest import MembershipFactory, RoleFactory, UserFactory

    role = RoleFactory(school=school, name="student")
    user = UserFactory(full_name="طالب الاختبار")
    MembershipFactory(user=user, school=school, role=role)
    return user


def _day(school, class_group, teacher, subject, student, on, marks):
    """يومٌ بحصصٍ عدّتها `len(marks)`؛ كل عنصر (status, excuse_type)."""
    for i, (status, excuse) in enumerate(marks):
        session = Session.objects.create(
            school=school,
            class_group=class_group,
            teacher=teacher,
            subject=subject,
            date=on,
            start_time=time(8 + i, 0),
            end_time=time(8 + i, 45),
            status="scheduled",
        )
        StudentAttendance.objects.create(
            session=session,
            student=student,
            school=school,
            status=status,
            excuse_type=excuse,
        )


@pytest.fixture
def seeded_year(db, school):
    from django.core.management import call_command

    call_command("seed_academic_calendar", school=school.code, verbosity=0)
    from core.academic_calendar import academic_year_window

    return academic_year_window(school)


def test_a_full_day_of_unexcused_absence_counts_as_one_day(
    db, school, class_group, teacher_user, subject, student, seeded_year
):
    start, _ = seeded_year
    _day(school, class_group, teacher_user, subject, student, start, [("absent", "")] * 7)

    standing = standing_for(student, school, grade="G7", on=start)

    assert standing.unexcused_days == 1
    assert standing.partial_days == 0


def test_missing_one_period_is_not_missing_a_day(
    db, school, class_group, teacher_user, subject, student, seeded_year
):
    """الخلط القديم كان يعدّ هذه الحصّة كأنها يوم."""
    start, _ = seeded_year
    marks = [("absent", "")] + [("present", "")] * 6
    _day(school, class_group, teacher_user, subject, student, start, marks)

    standing = standing_for(student, school, grade="G7", on=start)

    assert standing.unexcused_days == 0
    assert standing.partial_days == 1, "يُعرض ولا يُحتسب"


def test_an_excused_day_does_not_count(
    db, school, class_group, teacher_user, subject, student, seeded_year
):
    start, _ = seeded_year
    _day(
        school,
        class_group,
        teacher_user,
        subject,
        student,
        start,
        [("absent", "medical")] * 7,
    )

    standing = standing_for(student, school, grade="G7", on=start)

    assert standing.unexcused_days == 0
    assert standing.excused_days == 1


def test_the_count_is_cumulative_and_days_need_not_be_consecutive(
    db, school, class_group, teacher_user, subject, student, seeded_year
):
    """النصّ: «متصلة أو غير متصلة، اعتباراً من بداية العام الدراسي»."""
    start, _ = seeded_year
    for offset in (0, 5, 11, 30):
        _day(
            school,
            class_group,
            teacher_user,
            subject,
            student,
            start + timedelta(days=offset),
            [("absent", "")] * 3,
        )

    standing = standing_for(student, school, grade="G7", on=start + timedelta(days=40))

    assert standing.unexcused_days == 4


def test_the_fifth_day_does_not_deprive_but_the_sixth_does(
    db, school, class_group, teacher_user, subject, student, seeded_year
):
    """«في حال تجاوز» — فالخامس نفسه لا يحرم، والسادس يحرم.

    والعددُ خمسةٌ لا سبعة: «الدليل التنظيمي لسياسة إدارة سلوك الطلبة 2026»
    م 3.4.1.3 نسخ أرقامَ سياسة 2018.
    """
    start, _ = seeded_year
    for offset in range(5):
        _day(
            school,
            class_group,
            teacher_user,
            subject,
            student,
            start + timedelta(days=offset),
            [("absent", "")] * 2,
        )

    at_five = standing_for(student, school, grade="G7", on=start + timedelta(days=10))
    assert at_five.unexcused_days == 5
    assert at_five.breached == ()
    assert at_five.upcoming.key == "s1_midterm"
    assert at_five.days_to_next == 0

    _day(
        school,
        class_group,
        teacher_user,
        subject,
        student,
        start + timedelta(days=6),
        [("absent", "")] * 2,
    )
    at_six = standing_for(student, school, grade="G7", on=start + timedelta(days=10))

    assert at_six.unexcused_days == 6
    assert [g.key for g in at_six.breached] == ["s1_midterm"]
    assert at_six.upcoming.key == "s1_final"


def test_grade_twelve_survives_six_days_where_grade_seven_does_not(
    db, school, class_group, teacher_user, subject, student, seeded_year
):
    """الجدولان يختلفان بنيوياً — لا في الأرقام وحدها.

    عتبتا المنتصف مقصورتان على «الأول إلى الحادي عشر» بنصّ الدليل، فأوّلُ
    عتبةٍ تُصيب الثاني عشر هي ثمانيةٌ لا خمسة.
    """
    start, _ = seeded_year
    for offset in range(6):
        _day(
            school,
            class_group,
            teacher_user,
            subject,
            student,
            start + timedelta(days=offset),
            [("absent", "")] * 2,
        )
    on = start + timedelta(days=10)

    assert [g.key for g in standing_for(student, school, "G7", on).breached] == ["s1_midterm"]
    assert standing_for(student, school, "G12", on).breached == ()


def test_a_student_with_no_records_stands_clear(
    db, school, class_group, teacher_user, subject, student, seeded_year
):
    standing = standing_for(student, school, grade="G7", on=date.today())

    assert standing.unexcused_days == 0
    assert standing.upcoming.key == "s1_midterm"
    assert standing.days_to_next == 5


def test_the_gates_come_from_the_grade_not_from_the_calendar(db, school, student):
    """قبل بذر التقويم لا ينكسر شيء.

    كتبتُ هذا الاختبار أوّلاً يتوقّع `gates == ()` قبل البذر — وكان خطأً في
    الفهم: النافذة ترتدّ إلى سبتمبر–يونيو المشتقّين من اسم العام، فلا تُعيد
    `None` لمدرسةٍ لها عام. والعتبات تأتي من صفّ الطالب لا من التقويم أصلاً.
    """
    standing = standing_for(student, school, grade="G7")

    assert standing.unexcused_days == 0
    assert [g.max_days for g in standing.gates] == [5, 8, 11, 15]
    assert standing.upcoming.key == "s1_midterm"

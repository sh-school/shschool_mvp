"""[UX] صفحة الطالب تعرض موقفه من عتبات الغياب — ولا تحجب شيئاً.

وفي الصفحة نفسها كان ملخّص الحضور يُرشَّح بـ`session__date__year=` — أي
**السنة الميلادية**. والعام الدراسي يمتدّ من أغسطس إلى أغسطس، فكانت الصفحة
تعرض شطره الواقع في السنة الجارية وحده: في سبتمبر ثلاثة أسابيع، وفي يناير
يسقط الفصل الأول كلّه. ولا شيء يقول إن الرقم ناقص — والنسبة المئوية تبدو
سليمة لأنها نسبةٌ من مقامٍ ناقصٍ هو الآخر.
"""

from datetime import time, timedelta

import pytest
from django.urls import reverse

from operations.models import Session, StudentAttendance, Subject


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
    """التسجيل يجب أن يقع في العام الذي تشتقّه الواجهة.

    و`class_group` يُنشأ قبل بذر التقويم، فيأخذ العام المرتدّ إلى الثابت.
    فتبحث الواجهة عن العام المشتقّ ولا تجد تسجيلاً — ولا صفَّ للطالب،
    ولا صفَّ يعني لا جدولَ عتبات.
    """
    from core.academic_calendar import academic_year_for_school
    from core.models import StudentEnrollment
    from tests.conftest import MembershipFactory, RoleFactory, UserFactory

    class_group.academic_year = academic_year_for_school(school)
    class_group.save(update_fields=["academic_year"])

    role = RoleFactory(school=school, name="student")
    user = UserFactory(full_name="طالب الاختبار")
    MembershipFactory(user=user, school=school, role=role)
    StudentEnrollment.objects.create(student=user, class_group=class_group, is_active=True)
    return user


def _absent_days(school, class_group, teacher, subject, student, start, count):
    for offset in range(count):
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


def _page(client, principal_user, student):
    client.force_login(principal_user)
    return client.get(reverse("student_affairs:student_profile", args=[student.id]))


def test_the_page_shows_the_gates_and_names_its_source(
    client, db, school, principal_user, class_group, teacher_user, subject, student, year_window
):
    start, _ = year_window
    _absent_days(school, class_group, teacher_user, subject, student, start, 3)

    resp = _page(client, principal_user, student)
    body = resp.content.decode()

    assert resp.status_code == 200
    assert "عتبات الغياب" in body
    assert "سياسة تقييم الطلبة" in body, "رقمٌ بلا مصدرٍ على الشاشة لا يُراجَع"
    assert "قرار الحرمان لإدارة المدرسة" in body, "العرض يقول صراحةً إنه لا يحجب"


def test_the_page_counts_days_not_sessions(
    client, db, school, principal_user, class_group, teacher_user, subject, student, year_window
):
    start, _ = year_window
    _absent_days(school, class_group, teacher_user, subject, student, start, 3)

    ctx = _page(client, principal_user, student).context

    assert ctx["absence_standing"].unexcused_days == 3


def test_the_attendance_summary_covers_the_academic_year_not_the_calendar_year(
    client, db, school, principal_user, class_group, teacher_user, subject, student, year_window
):
    """العام يمتدّ عبر سنتين ميلاديتين — والترشيح القديم يقطعه عند رأس السنة."""
    start, end = year_window
    assert start.year != end.year, "المقدّمة: العام يعبر سنتين"

    _absent_days(school, class_group, teacher_user, subject, student, start, 2)
    # يومٌ في الشطر الثاني من العام — أي في السنة الميلادية التالية
    _absent_days(school, class_group, teacher_user, subject, student, end - timedelta(days=5), 1)

    ctx = _page(client, principal_user, student).context

    assert ctx["attendance"]["absent"] == 3, "الترشيح الميلاديّ كان يُسقط أحد الشطرين"


def test_no_gate_table_is_shown_for_a_grade_the_policy_does_not_cover(
    client, db, school, principal_user, student, year_window
):
    """الصفوف ١–٣ لها قسمٌ مستقلّ لم يُشفَّر — فلا جدول بدل جدولٍ خاطئ."""
    from operations.absence_standing import standing_for

    standing = standing_for(student, school, grade="G2")

    assert standing.has_no_policy
    assert standing.gates == ()

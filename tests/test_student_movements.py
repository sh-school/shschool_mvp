"""[STUDENT_AFFAIRS] SOS-20260915-9077: شاشة تحركات الطلبة.

طلب سلطان الهاجرى: شاشةٌ كشاشة الغياب لخروج الطالب أثناء الحصّة (عيادة/
إدارة/دورة مياه/أخرى). تُقرأ من `ClassExit` — البنية التي يكتبها زرّ «خرج
بإذن» أصلاً (`operations.class_exit`) — لا نسخةٌ ثانية. والمشرفُ يرى
تحركات جناحه فقط (قرارُ 2026-09-14/15، `wings.scope`)، كسائر شاشات
المتابعة.
"""

import datetime as dt

import pytest
from django.urls import reverse
from django.utils import timezone

from core.academic_calendar import academic_year_for_school
from core.models import Wing
from operations.models import ClassExit, Session
from tests.conftest import (
    ClassGroupFactory,
    MembershipFactory,
    RoleFactory,
    StudentEnrollmentFactory,
    UserFactory,
)

pytestmark = pytest.mark.django_db

DAY = dt.date(2026, 9, 20)


@pytest.fixture
def year(school):
    return academic_year_for_school(school)


@pytest.fixture
def wing_a(school, year):
    klass = ClassGroupFactory(school=school, academic_year=year)
    supervisor = UserFactory(full_name="مشرف الجناح أ", national_id="29400000001")
    MembershipFactory(
        user=supervisor, school=school, role=RoleFactory(school=school, name="admin_supervisor")
    )
    wing = Wing.objects.create(
        school=school, code="wa", name="جناح أ", academic_year=year, supervisor=supervisor
    )
    klass.wing = wing
    klass.save(update_fields=["wing"])
    return klass, supervisor


@pytest.fixture
def wing_b(school, year):
    klass = ClassGroupFactory(school=school, academic_year=year)
    supervisor = UserFactory(full_name="مشرف الجناح ب", national_id="29400000002")
    MembershipFactory(
        user=supervisor, school=school, role=RoleFactory(school=school, name="admin_supervisor")
    )
    wing = Wing.objects.create(
        school=school, code="wb", name="جناح ب", academic_year=year, supervisor=supervisor
    )
    klass.wing = wing
    klass.save(update_fields=["wing"])
    return klass, supervisor


def _exit_in(school, klass, teacher, student, destination="clinic", hour=8):
    """جلسةٌ وخروجٌ منها — `hour` يفرّق حصصَ المعلّم نفسه في اليوم نفسه، فلا
    يصطدم قيدُ «لا تداخل لمعلّم» (`no_teacher_time_overlap`) حين يُستدعى
    مرّتين لمعلّمٍ واحد في اختبارٍ واحد.

    وتسجيلُ الطالب في الشعبة إلزاميّ هنا: تضييقُ `wings.scope` بجناح
    المشرف يقرأ `StudentEnrollment` لا شعبةَ الحصّة — طالبٌ بلا قيدٍ نشطٍ
    لا يظهر لأيّ مشرف مهما كانت حصّتُه."""
    StudentEnrollmentFactory(student=student, class_group=klass)
    session = Session.objects.create(
        school=school,
        class_group=klass,
        teacher=teacher,
        date=DAY,
        start_time=dt.time(hour, 0),
        end_time=dt.time(hour, 40),
        status="scheduled",
    )
    return ClassExit.objects.create(
        school=school,
        session=session,
        student=student,
        destination=destination,
        left_at=timezone.make_aware(dt.datetime.combine(DAY, dt.time(hour, 5))),
        allowed_by=teacher,
    )


def test_leadership_sees_every_wing(client, school, principal_user, teacher_user, wing_a, wing_b):
    klass_a, _ = wing_a
    klass_b, _ = wing_b
    student_a = UserFactory(full_name="طالب أ", national_id="29400000011")
    student_b = UserFactory(full_name="طالب ب", national_id="29400000012")
    _exit_in(school, klass_a, teacher_user, student_a, hour=8)
    _exit_in(school, klass_b, teacher_user, student_b, hour=9)
    client.force_login(principal_user)

    html = client.get(
        reverse("student_affairs:student_movements"), {"date": DAY.isoformat()}
    ).content.decode()

    assert "طالب أ" in html
    assert "طالب ب" in html


def test_supervisor_sees_own_wing_only(client, school, teacher_user, wing_a, wing_b):
    klass_a, supervisor_a = wing_a
    klass_b, _ = wing_b
    student_a = UserFactory(full_name="طالب أ", national_id="29400000021")
    student_b = UserFactory(full_name="طالب ب", national_id="29400000022")
    _exit_in(school, klass_a, teacher_user, student_a, hour=8)
    _exit_in(school, klass_b, teacher_user, student_b, hour=9)
    client.force_login(supervisor_a)

    html = client.get(
        reverse("student_affairs:student_movements"), {"date": DAY.isoformat()}
    ).content.decode()

    assert "طالب أ" in html
    assert "طالب ب" not in html


def test_destination_filter_narrows_the_list(client, school, principal_user, teacher_user, wing_a):
    klass_a, _ = wing_a
    student_clinic = UserFactory(full_name="طالب العيادة", national_id="29400000031")
    student_restroom = UserFactory(full_name="طالب دورة المياه", national_id="29400000032")
    _exit_in(school, klass_a, teacher_user, student_clinic, destination="clinic", hour=8)
    _exit_in(school, klass_a, teacher_user, student_restroom, destination="restroom", hour=9)
    client.force_login(principal_user)

    html = client.get(
        reverse("student_affairs:student_movements"),
        {"date": DAY.isoformat(), "destination": "clinic"},
    ).content.decode()

    assert "طالب العيادة" in html
    assert "طالب دورة المياه" not in html


def test_the_four_destination_cards_render_including_a_zero_one(
    client, school, principal_user, teacher_user, wing_a
):
    """طلب المدير (تذكرة رقم 10): بطاقةٌ لكلّ وجهة — عيادة، إدارة، دورة
    مياه، وخروج من المدرسة (ثابتةٌ صفراً عمداً، غير مُسجَّلة بعد).

    ويوم فيه خروجٌ للعيادة وحدها يجب ألّا يُسقط الاستمارةَ حين تُبنى بطاقةُ
    وجهةٍ لا خروج لها ذلك اليوم (`destination_counts.get(code, 0)`) — هذا
    بالضبط ما كسر الشاشةَ (`TemplateSyntaxError: kpi «...»: الرقم مطلوب`)
    حين كان التجميع يُخرج صفوفاً أحاديّة العنصر لا يبنيها `dict()` بقيمة."""
    klass_a, _ = wing_a
    student = UserFactory(full_name="طالب العيادة الوحيد", national_id="29400000051")
    _exit_in(school, klass_a, teacher_user, student, destination="clinic", hour=8)
    client.force_login(principal_user)

    resp = client.get(reverse("student_affairs:student_movements"), {"date": DAY.isoformat()})
    html = resp.content.decode()

    assert resp.status_code == 200
    assert "مراجعة العيادة" in html
    assert "مراجعة الإدارة" in html
    assert "دورة المياه" in html
    assert "الخروج من المدرسة" in html


def test_open_status_filter_shows_only_those_who_have_not_returned(
    client, school, principal_user, teacher_user, wing_a
):
    klass_a, _ = wing_a
    still_out = UserFactory(full_name="لم يعد بعد", national_id="29400000041")
    returned = UserFactory(full_name="عاد بالفعل", national_id="29400000042")
    _exit_in(school, klass_a, teacher_user, still_out, hour=8)
    closed = _exit_in(school, klass_a, teacher_user, returned, hour=9)
    closed.returned_at = timezone.make_aware(dt.datetime.combine(DAY, dt.time(9, 15)))
    closed.save(update_fields=["returned_at"])
    client.force_login(principal_user)

    html = client.get(
        reverse("student_affairs:student_movements"),
        {"date": DAY.isoformat(), "status": "open"},
    ).content.decode()

    assert "لم يعد بعد" in html
    assert "عاد بالفعل" not in html

"""[STUDENT_AFFAIRS] SOS-20260915-9077: شاشة تحركات الطلبة.

الطلب: شاشةٌ كشاشة الغياب لخروج الطالب أثناء الحصّة (عيادة/
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
    مياه، وخروجٌ مبكرٌ من المدرسة (غيرُ مُسجَّلٍ بعد).

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
    assert "الخروج مبكراً من المدرسة" in html
    assert 'class="action-card' in html, "البطاقاتُ الأربع بلاطاتٌ حقيقيّة — لا أرقامٌ عارية"


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


# ═════════════════════════════════════════════════════════════════════
# W-20261105-009: قيدٌ ونقلٌ وانسحابٌ وتغيير شعبة بنطاق المدرسة
# ═════════════════════════════════════════════════════════════════════


def _student(school, name, nid):
    user = UserFactory(full_name=name, national_id=nid)
    MembershipFactory(user=user, school=school, role=RoleFactory(school=school, name="student"))
    return user


@pytest.fixture
def movement_data(school, year):
    """قيدٌ في أ، وتغييرُ شعبةٍ أ←ب، ونقلٌ صادر، وانسحاب، وطالبٌ في مدرسةٍ أخرى."""
    from core.models import School
    from student_affairs.models import StudentTransfer

    a = ClassGroupFactory(school=school, academic_year=year, grade="G10", section="1")
    b = ClassGroupFactory(school=school, academic_year=year, grade="G10", section="2")
    enrolled = _student(school, "طالب مقيَّد", "29500000001")
    StudentEnrollmentFactory(student=enrolled, class_group=a, enrolled_at=dt.date(2026, 9, 1))

    mover = _student(school, "طالب تغيّرت شعبته", "29500000002")
    StudentEnrollmentFactory(
        student=mover,
        class_group=a,
        is_active=False,
        enrolled_at=dt.date(2026, 9, 1),
        left_at=dt.date(2026, 10, 9),
    )
    StudentEnrollmentFactory(student=mover, class_group=b, enrolled_at=dt.date(2026, 10, 10))
    StudentTransfer.objects.create(
        school=school,
        student=mover,
        direction="internal",
        other_school_name=school.name,
        to_class_group=b,
        transfer_date=dt.date(2026, 10, 10),
        status="completed",
        academic_year=year,
    )

    out = _student(school, "طالب منقول", "29500000003")
    StudentEnrollmentFactory(student=out, class_group=b, enrolled_at=dt.date(2026, 9, 1))
    StudentTransfer.objects.create(
        school=school,
        student=out,
        direction="out",
        other_school_name="مدرسة الأمل",
        transfer_date=dt.date(2026, 11, 1),
        status="completed",
        academic_year=year,
    )

    gone = _student(school, "طالب منسحب", "29500000004")
    StudentEnrollmentFactory(student=gone, class_group=a, enrolled_at=dt.date(2026, 9, 1))
    membership = gone.memberships.first()
    # الالتحاق الافتراضيّ اليوم؛ والانسحابُ قبله لا يستقيم — فنقدِّم الالتحاق إلى بداية العام
    membership.joined_at = dt.date(2026, 9, 1)
    membership.save(update_fields=["joined_at"])
    membership.record_departure(on=dt.date(2026, 10, 20), reason="other", reference="قرار 5")

    # مدرسةٌ أخرى: لا يجوز أن يظهر طالبُها
    other = School.objects.create(name="مدرسة أخرى", code="OTH1")
    foreign = _student(other, "طالب مدرسة أخرى", "29500000005")
    foreign_class = ClassGroupFactory(school=other, academic_year=year)
    StudentEnrollmentFactory(student=foreign, class_group=foreign_class)
    return a, b


URL = "student_affairs:enrollment_movements"


def test_movements_list_has_all_four_kinds_school_scoped(client, principal_user, movement_data):
    client.force_login(principal_user)
    html = client.get(reverse(URL)).content.decode()

    for label in ("قيد", "نقل صادر", "انسحاب", "تغيير شعبة"):
        assert label in html
    assert "طالب تغيّرت شعبته" in html
    assert "مدرسة الأمل" in html
    assert "طالب مدرسة أخرى" not in html


def test_internal_transfer_enrolment_is_not_counted_as_enrol(school, movement_data):
    from student_affairs.selectors import enrollment_movements

    rows = enrollment_movements(school)
    mover_kinds = [r["kind"] for r in rows if r["student"].full_name == "طالب تغيّرت شعبته"]
    assert sorted(mover_kinds) == ["enrol", "section_change"]  # القيدُ الأوّل فقط


def test_filter_by_class_and_period(client, principal_user, movement_data):
    _, b = movement_data
    client.force_login(principal_user)

    html = client.get(reverse(URL), {"class_group": str(b.pk)}).content.decode()
    assert "طالب منقول" in html
    assert "طالب مقيَّد" not in html

    html = client.get(reverse(URL), {"from": "2026-10-15", "to": "2026-10-31"}).content.decode()
    assert "طالب منسحب" in html
    assert "طالب منقول" not in html

    html = client.get(reverse(URL), {"kind": "withdraw"}).content.decode()
    assert "طالب منسحب" in html
    assert "طالب مقيَّد" not in html


def test_bad_filters_do_not_break_the_page(client, principal_user, movement_data):
    client.force_login(principal_user)
    resp = client.get(reverse(URL), {"from": "xx", "class_group": "not-a-uuid"})
    assert resp.status_code == 200


def test_export_respects_filters_and_hides_national_id(client, principal_user, movement_data):
    import io

    import openpyxl
    from django.http import QueryDict

    from core.exports.runner import run_job
    from core.models import ExportJob

    client.force_login(principal_user)
    resp = client.get(reverse("student_affairs:enrollment_movements_export"), {"kind": "withdraw"})

    # التصديرُ مهمّةٌ خلفيّة: الطلبُ يُنشئها ثمّ يبنيها العامل بالمرشِّحات المحفوظة
    assert resp.status_code == 302
    job = ExportJob.objects.get(kind="student_affairs.movements_xlsx")
    assert QueryDict(job.query_string)["kind"] == "withdraw"
    run_job(str(job.id))
    job.refresh_from_db()
    assert job.status == "done"
    ws = openpyxl.load_workbook(io.BytesIO(bytes(job.content))).active
    cells = [str(c.value) for row in ws.iter_rows() for c in row]
    assert "طالب منسحب" in cells
    assert "طالب مقيَّد" not in cells
    assert not any("29500000004" in c for c in cells)


def test_coordinator_allowed_teacher_and_supervisor_denied(
    client, student_affairs_coordinator_user, teacher_user, admin_supervisor_user, movement_data
):
    client.force_login(student_affairs_coordinator_user)
    assert client.get(reverse(URL)).status_code == 200

    for user in (teacher_user, admin_supervisor_user):
        client.force_login(user)
        assert client.get(reverse(URL)).status_code in (302, 403)
        export = client.get(reverse("student_affairs:enrollment_movements_export"))
        assert export.status_code in (302, 403)

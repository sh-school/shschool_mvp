"""[STUDENT_AFFAIRS] SOS-20260915-9077: شاشة تحركات الطلبة.

الطلب: شاشةٌ كشاشة الغياب لخروج الطالب أثناء الحصّة (عيادة/
إدارة/دورة مياه/أخرى). تُقرأ من `ClassExit` — البنية التي يكتبها زرّ «خرج
بإذن» أصلاً (`operations.class_exit`) — لا نسخةٌ ثانية. والمشرفُ يرى
تحركات جناحه فقط (قرارُ 2026-09-14/15، `wings.scope`)، كسائر شاشات
المتابعة.
"""

import datetime as dt
import re
from html import unescape
from io import BytesIO
from urllib.parse import parse_qs

import pytest
from django.urls import reverse
from django.utils import timezone

from core.academic_calendar import academic_year_for_school
from core.models import Wing
from operations.models import ClassExit, Session
from student_affairs.models import StudentTransfer
from student_affairs.selectors import enrolment_movements
from tests.conftest import (
    ClassGroupFactory,
    MembershipFactory,
    RoleFactory,
    SchoolFactory,
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


# ── W-20261106-016: قيدٌ ونقلٌ وانسحابٌ وتغييرُ شعبة (شاشةٌ غيرُ شاشة الخروج من الحصّة) ──

ENROL_URL = "student_affairs:enrolment_movements"
D1, D2, D3 = dt.date(2026, 9, 1), dt.date(2026, 10, 1), dt.date(2026, 11, 1)


@pytest.fixture
def groups(school, year):
    return (
        ClassGroupFactory(school=school, academic_year=year, grade="G7", section="أ"),
        ClassGroupFactory(school=school, academic_year=year, grade="G7", section="ب"),
    )


def _enrol(student, group, day, **kw):
    return StudentEnrollmentFactory(student=student, class_group=group, enrolled_at=day, **kw)


def _completed_transfer(school, year, student, direction, other, day):
    return StudentTransfer.objects.create(
        school=school,
        student=student,
        direction=direction,
        other_school_name=other,
        transfer_date=day,
        status="completed",
        academic_year=year,
    )


@pytest.fixture
def movements(school, year, groups):
    """قيدٌ، وتغييرُ شعبة، وانسحابٌ، ونقلٌ صادرٌ، ونقلٌ وارد."""
    a, b = groups
    _enrol(UserFactory(full_name="طالب مقيَّد"), a, D1)

    changer = UserFactory(full_name="طالب مُحوَّل")
    old = D1 - dt.timedelta(days=30)
    _enrol(changer, a, old, is_active=False, left_at=D2 - dt.timedelta(days=1))
    _enrol(changer, b, D2)

    quitter = UserFactory(full_name="طالب منسحب")
    _enrol(quitter, a, D1 - dt.timedelta(days=60), is_active=False, left_at=D3)

    leaver = UserFactory(full_name="طالب منقول")
    _enrol(leaver, b, D1 - dt.timedelta(days=60), is_active=False, left_at=D3)
    _completed_transfer(school, year, leaver, "out", "مدرسة الشمال", D3)

    arrival = UserFactory(full_name="طالب وارد")
    _enrol(arrival, b, D2)
    _completed_transfer(school, year, arrival, "in", "مدرسة الجنوب", D2)


def _kinds(events):
    return sorted((e["student"].full_name, e["kind"]) for e in events)


def test_list_has_every_kind_newest_first(school, year, movements):
    events = enrolment_movements(school, year)
    assert _kinds(events) == sorted(
        [
            ("طالب مقيَّد", "enrol"),
            ("طالب مُحوَّل", "enrol"),
            ("طالب مُحوَّل", "section_change"),
            ("طالب منسحب", "enrol"),
            ("طالب منسحب", "withdrawal"),
            ("طالب منقول", "enrol"),
            ("طالب منقول", "transfer_out"),
            ("طالب وارد", "transfer_in"),
        ]
    )
    dates = [e["date"] for e in events]
    assert dates == sorted(dates, reverse=True)


def test_section_change_names_both_sections(school, year, movements):
    (change,) = enrolment_movements(school, year, kind="section_change")
    assert change["from_text"] != change["class_text"]
    assert change["date"] == D2


def test_filter_by_section_matches_origin_and_destination(school, year, groups, movements):
    a, _ = groups
    found = _kinds(enrolment_movements(school, year, class_group_id=a.id))
    assert ("طالب مُحوَّل", "section_change") in found  # غادر الشعبة أ
    assert ("طالب وارد", "transfer_in") not in found


def test_filter_by_period_and_kind(school, year, movements):
    assert {e["date"] for e in enrolment_movements(school, year, date_from=D3)} == {D3}
    before = enrolment_movements(school, year, date_to=D2 - dt.timedelta(days=1))
    assert before and all(e["date"] < D2 for e in before)
    kinds = {e["kind"] for e in enrolment_movements(school, year, kind="withdrawal")}
    assert kinds == {"withdrawal"}


def test_other_school_and_other_year_are_invisible(school, year, movements):
    group = ClassGroupFactory(school=SchoolFactory(), academic_year=year)
    _enrol(UserFactory(full_name="طالب مدرسة أخرى"), group, D1)
    names = {e["student"].full_name for e in enrolment_movements(school, year)}
    assert "طالب مدرسة أخرى" not in names
    assert enrolment_movements(school, "1999-2000") == []


def test_continuing_student_is_not_a_new_enrolment(school, year, groups):
    old = ClassGroupFactory(school=school, academic_year="1999-2000")
    student = UserFactory(full_name="طالب مستمر")
    _enrol(student, old, dt.date(1999, 9, 1), is_active=False)
    _enrol(student, groups[0], D1)
    assert enrolment_movements(school, year) == []


def test_enrolment_screen_for_coordinator(client_as, student_affairs_coordinator_user, movements):
    resp = client_as(student_affairs_coordinator_user).get(reverse(ENROL_URL))
    body = resp.content.decode()
    assert resp.status_code == 200
    assert "طالب منقول" in body and "نقل صادر" in body and "مدرسة الشمال" in body


def test_enrolment_screen_filters(client_as, student_affairs_coordinator_user, movements):
    resp = client_as(student_affairs_coordinator_user).get(
        reverse(ENROL_URL), {"kind": "withdrawal", "from": D3.isoformat()}
    )
    body = resp.content.decode()
    assert "طالب منسحب" in body and "طالب مقيَّد" not in body


def test_enrolment_screen_ignores_a_bad_date(
    client_as, student_affairs_coordinator_user, movements
):
    assert (
        client_as(student_affairs_coordinator_user)
        .get(reverse(ENROL_URL), {"from": "xx"})
        .status_code
        == 200
    )


def test_enrolment_screen_open_to_leadership(client_as, principal_user, movements):
    assert client_as(principal_user).get(reverse(ENROL_URL)).status_code == 200


def test_enrolment_screen_refuses_others(client_as, client, teacher_user, student_user, movements):
    export = reverse("student_affairs:enrolment_movements_export")
    assert client_as(teacher_user).get(reverse(ENROL_URL)).status_code == 403
    assert client_as(teacher_user).get(export).status_code == 403
    assert client_as(student_user).get(reverse(ENROL_URL)).status_code == 403
    client.logout()
    assert client.get(reverse(ENROL_URL)).status_code == 302


def test_link_to_enrolment_screen_follows_the_capability(client_as, principal_user, teacher_user):
    """الرابطُ في القائمة نفسها بنمط `can_open`: يظهر لمن يملك `student_affairs.transfers`، ويغيب عمّن لا يملكه."""
    link = f'href="{reverse(ENROL_URL)}"'
    assert link in client_as(principal_user).get(reverse("dashboard")).content.decode()
    assert link not in client_as(teacher_user).get(reverse("dashboard")).content.decode()


@pytest.fixture
def many_enrolments(school, year, groups):
    """ثلاثةٌ وخمسون قيداً جديداً في الشعبة أ — يتجاوز صفحةً واحدةً من 50."""
    a, _ = groups
    for i in range(53):
        _enrol(UserFactory(full_name=f"طالب ترقيم {i:03d}"), a, D1)
    return a


def test_list_is_split_into_pages_of_fifty(
    client_as, student_affairs_coordinator_user, many_enrolments
):
    a = many_enrolments
    client = client_as(student_affairs_coordinator_user)
    query = {"section": a.id, "kind": "enrol"}

    first = client.get(reverse(ENROL_URL), query)
    assert first.status_code == 200
    assert len(first.context["page_obj"]) == 50
    assert first.content.decode().count('class="sa-link"') == 50
    assert "صفحة 1 من 2" in first.content.decode()

    second = client.get(reverse(ENROL_URL), {**query, "page": 2})
    body = second.content.decode()
    assert len(second.context["page_obj"]) == 3
    assert body.count('class="sa-link"') == 3

    # رابطُ «السابقة» في الصفحة الثانية يحمل الترشيحَ كاملاً ويُبدّل `page` وحده.
    prev = re.search(r'href="\?([^"]+)"[^>]*?aria-label="الصفحة السابقة"', body)
    assert prev, "رابطُ الصفحة السابقة غائب"
    assert parse_qs(unescape(prev.group(1))) == {
        "section": [str(a.id)],
        "kind": ["enrol"],
        "page": ["1"],
    }


def test_export_covers_every_row_not_just_the_page(
    school, student_affairs_coordinator_user, many_enrolments
):
    """التصدير لا يتقيّد بالصفحة: كلُّ ما يطابق المرشِّحات (53) يخرج في الملفّ."""
    from django.http import QueryDict

    from student_affairs.export_builders import build_movements_xlsx

    result = build_movements_xlsx(
        school,
        student_affairs_coordinator_user,
        QueryDict(f"section={many_enrolments.id}&kind=enrol"),
    )
    assert result.rows == 53


def test_enrolment_export_is_a_registered_background_kind(school):
    from core.exports import registry

    spec = registry.get("student_affairs.movements_xlsx")
    assert spec is not None and spec.mode == "job"
    assert spec.capability == "student_affairs.transfers"


def test_enrolment_export_view_starts_a_job_for_the_coordinator(
    client_as, student_affairs_coordinator_user, movements
):
    resp = client_as(student_affairs_coordinator_user).get(
        reverse("student_affairs:enrolment_movements_export"), {"kind": "withdrawal"}
    )
    assert resp.status_code != 403 and resp.status_code < 400


def test_enrolment_export_follows_filters(school, student_affairs_coordinator_user, movements):
    import openpyxl
    from django.http import QueryDict

    from student_affairs.export_builders import build_movements_xlsx

    result = build_movements_xlsx(
        school, student_affairs_coordinator_user, QueryDict("kind=withdrawal")
    )
    assert result.rows == 1 and result.full_national_id is False
    ws = openpyxl.load_workbook(BytesIO(result.content)).active
    cells = [c.value for row in ws.iter_rows() for c in row if c.value]
    assert "طالب منسحب" in cells and "انسحاب" in cells
    assert "طالب مقيَّد" not in cells

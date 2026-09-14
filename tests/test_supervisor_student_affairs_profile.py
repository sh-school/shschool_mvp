"""[SECURITY] شؤون الطلبة للمشرف الإداريّ — لوحتُه وسجلُّه وملفُّ الطالب لطلبة جناحه وحدَهم.

قرارا المستخدم 2026-09-14 و2026-09-15 اللذان تحرسهما هذه الاختبارات:
- المشرفُ يفتح لوحةَ شؤون الطلبة وسجلَّ الطلبة وملفَّ الطالب ونسختَه PDF ومرفقَ عذر
  التأخّر — مقيَّدةً كلُّها بجناحه. ورابطُ طالبٍ خارجه 404 لا يُميَّز عن غير الموجود،
  و`?year=` لا يوسّع نطاقَه.
- وتبقى مغلقةً عليه: الإضافةُ والتعديلُ والإيقافُ والانتقالاتُ وتصديرُ السجلّ كلِّه
  وجزئيّةُ الجدول.
- ولا يرى وإن كان الطالبُ من جناحه: الدرجات، وفصيلةَ الدم وأسبابَ زيارات العيادة
  (يرى التاريخَ و«أُرسل للمنزل» وحدَهما)، والإعاراتِ والأنشطةَ والانتقالات. ونسختُه PDF
  بالرقم الشخصيّ مستوراً.
- والقيادةُ ترى ما كانت تراه: المدرسةَ كلَّها والأقسامَ كلَّها و`?year=` كما هو.
"""

import datetime as dt
import uuid
from unittest.mock import patch

import pytest
from django.db import connection
from django.http import HttpResponse
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

from core.models import AuditLog, Wing
from operations.models import Session, StudentAttendance
from tests.conftest import (
    BehaviorInfractionFactory,
    ClassGroupFactory,
    ClinicVisitFactory,
    HealthRecordFactory,
    MembershipFactory,
    RoleFactory,
    UserFactory,
)
from tests.test_period_register import (  # noqa: F401 — التجهيزاتُ نفسُها: جناح 1 ومشرفُه
    klass,
    supervisor,
    teacher,
    year,
)

pytestmark = pytest.mark.django_db

OUTSIDER_NID = "29400000077"


def _student(school, klass, name, national_id):
    """طالبٌ بعضويّةٍ وقيدٍ نشطٍ في `klass` — ملفُّ الطالب يشترط العضويّة."""
    from core.models import StudentEnrollment

    user = UserFactory(full_name=name, national_id=national_id)
    MembershipFactory(user=user, school=school, role=RoleFactory(school=school, name="student"))
    StudentEnrollment.objects.create(student=user, class_group=klass, is_active=True)
    return user


@pytest.fixture
def wing_kid(school, klass, supervisor):
    return _student(school, klass, "طالب الجناح الأوّل", "29400000011")


@pytest.fixture
def other_klass(school, year):
    """شعبةٌ في جناحٍ ثانٍ بمشرفٍ آخر — طلبتُها خارج نطاق مشرف جناح 1."""
    other = UserFactory(full_name="مشرف الجناح الثاني", national_id="29400000092")
    MembershipFactory(
        user=other, school=school, role=RoleFactory(school=school, name="admin_supervisor")
    )
    wing = Wing.objects.create(
        school=school, code="w2", name="جناح 2", academic_year=year, supervisor=other
    )
    return ClassGroupFactory(
        school=school, grade="G8", section="2", level_type="prep", academic_year=year, wing=wing
    )


@pytest.fixture
def outsider(school, other_klass):
    return _student(school, other_klass, "طالب الجناح الثاني", OUTSIDER_NID)


def _today_session(school, klass, teacher, hour):
    now = timezone.localdate()
    return Session.objects.create(
        school=school,
        class_group=klass,
        teacher=teacher,
        date=now,
        start_time=dt.time(hour, 10),
        end_time=dt.time(hour, 55),
        status="scheduled",
    )


# ══════════════════════════════════════════════════════════════════════
#  1. الحرّاس — ما يُفتح له وما يبقى مغلقاً
# ══════════════════════════════════════════════════════════════════════


class TestTheGates:
    @pytest.mark.parametrize("name", ["student_affairs:dashboard", "student_affairs:student_list"])
    def test_the_supervisor_opens_his_follow_up_screens(
        self, client_as, school, seeded_calendar, klass, supervisor, wing_kid, name
    ):
        assert client_as(supervisor).get(reverse(name)).status_code == 200

    def test_the_supervisor_opens_his_wing_students_file(
        self, client_as, school, seeded_calendar, klass, supervisor, wing_kid
    ):
        url = reverse("student_affairs:student_profile", args=[wing_kid.id])
        assert client_as(supervisor).get(url).status_code == 200

    @pytest.mark.parametrize(
        "name",
        [
            "student_affairs:student_add",
            "student_affairs:student_export",
            "student_affairs:student_table_partial",
            "student_affairs:transfer_list",
            "student_affairs:transfer_create",
        ],
    )
    def test_the_register_writing_screens_stay_closed(
        self, client_as, school, seeded_calendar, klass, supervisor, name
    ):
        assert client_as(supervisor).get(reverse(name)).status_code == 403

    def test_editing_even_his_own_wing_student_stays_closed(
        self, client_as, school, seeded_calendar, klass, supervisor, wing_kid
    ):
        client = client_as(supervisor)
        edit = reverse("student_affairs:student_edit", args=[wing_kid.id])
        deactivate = reverse("student_affairs:student_deactivate", args=[wing_kid.id])
        review = reverse("student_affairs:transfer_review", args=[uuid.uuid4()])

        assert client.get(edit).status_code == 403
        assert client.post(deactivate).status_code == 403
        assert client.post(review, {"action": "completed"}).status_code == 403


# ══════════════════════════════════════════════════════════════════════
#  2. طالبُ جناحٍ آخر — 404 في كلّ باب
# ══════════════════════════════════════════════════════════════════════


class TestAnotherWingIsNotFound:
    @pytest.mark.parametrize(
        "name", ["student_affairs:student_profile", "student_affairs:student_profile_pdf"]
    )
    def test_the_file_of_another_wings_student_is_404_even_with_a_year(
        self, client_as, school, seeded_calendar, klass, supervisor, outsider, name
    ):
        url = reverse(name, args=[outsider.id])
        client = client_as(supervisor)

        assert client.get(url).status_code == 404
        assert client.get(url + "?year=2020-2021").status_code == 404

    @patch("student_affairs.views.render_pdf", return_value=HttpResponse(b"%PDF"))
    def test_leadership_still_opens_every_file(
        self, _pdf, client_as, school, seeded_calendar, klass, principal_user, outsider
    ):
        client = client_as(principal_user)
        for name in ("student_affairs:student_profile", "student_affairs:student_profile_pdf"):
            assert client.get(reverse(name, args=[outsider.id])).status_code == 200

    def test_the_tardiness_excuse_of_another_wing_is_404(
        self, client_as, school, seeded_calendar, klass, supervisor, teacher, wing_kid, outsider
    ):
        mine = _today_session(school, klass, teacher, 7)
        theirs = _today_session(school, outsider.enrollments.get().class_group, teacher, 8)
        StudentAttendance.objects.create(
            session=mine, student=wing_kid, school=school, status="late", excuse_file="ex/w1.pdf"
        )
        StudentAttendance.objects.create(
            session=theirs, student=outsider, school=school, status="late", excuse_file="ex/w2.pdf"
        )
        media = "student_affairs:protected_media"

        client = client_as(supervisor)
        assert client.get(reverse(media, args=["ex/w1.pdf"])).status_code == 200
        assert client.get(reverse(media, args=["ex/w2.pdf"])).status_code == 404

    def test_leadership_still_opens_every_excuse(
        self, client_as, school, seeded_calendar, klass, principal_user, teacher, outsider
    ):
        theirs = _today_session(school, outsider.enrollments.get().class_group, teacher, 8)
        StudentAttendance.objects.create(
            session=theirs, student=outsider, school=school, status="late", excuse_file="ex/w2.pdf"
        )
        url = reverse("student_affairs:protected_media", args=["ex/w2.pdf"])

        assert client_as(principal_user).get(url).status_code == 200


# ══════════════════════════════════════════════════════════════════════
#  3. اللوحة — أرقامُ جناحه لا أرقامُ المدرسة
# ══════════════════════════════════════════════════════════════════════


class TestTheDashboardCountsHisWing:
    @pytest.fixture
    def today(self, school, klass, teacher, wing_kid, outsider):
        """غائبان ومخالفتان اليوم — واحدٌ في كلّ جناح."""
        mine = _today_session(school, klass, teacher, 7)
        theirs = _today_session(school, outsider.enrollments.get().class_group, teacher, 8)
        StudentAttendance.objects.create(
            session=mine, student=wing_kid, school=school, status="absent"
        )
        StudentAttendance.objects.create(
            session=theirs, student=outsider, school=school, status="absent"
        )
        for kid in (wing_kid, outsider):
            BehaviorInfractionFactory(school=school, student=kid, date=timezone.localdate())

    def test_the_supervisor_sees_only_his_wing(
        self, client_as, school, seeded_calendar, klass, supervisor, wing_kid, outsider, today
    ):
        ctx = client_as(supervisor).get(reverse("student_affairs:dashboard")).context

        assert ctx["total_students"] == 1
        assert ctx["absent_today"] == 1
        assert [s["full_name"] for s in ctx["absent_list"]] == [wing_kid.full_name]
        assert ctx["today_behavior_count"] == 1
        assert [row["student"] for row in ctx["infraction_rows"]] == [wing_kid.full_name]
        assert [row["count"] for row in ctx["grade_rows"]] == [1]
        assert "طلبة جناحك" in ctx["page_subtitle"]

    def test_leadership_sees_the_whole_school(
        self, client_as, school, seeded_calendar, klass, principal_user, outsider, today
    ):
        ctx = client_as(principal_user).get(reverse("student_affairs:dashboard")).context

        assert ctx["total_students"] == 2
        assert ctx["absent_today"] == 2
        assert ctx["today_behavior_count"] == 2
        assert "طلبة جناحك" not in ctx["page_subtitle"]

    def test_a_supervisor_without_a_wing_sees_nothing_not_the_school(
        self, client_as, school, seeded_calendar, klass, wing_kid, outsider, today
    ):
        """قيودٌ فارغةٌ كاذبةٌ في بايثون — و`or` كان يردّها إلى قيود المدرسة كلِّها."""
        idle = UserFactory(full_name="مشرف بلا جناح", national_id="29400000093")
        MembershipFactory(
            user=idle, school=school, role=RoleFactory(school=school, name="admin_supervisor")
        )

        ctx = client_as(idle).get(reverse("student_affairs:dashboard")).context

        assert (ctx["total_students"], ctx["absent_today"], ctx["today_behavior_count"]) == (
            0,
            0,
            0,
        )
        assert ctx["stage_label"] == "إعدادي 0 · ثانوي 0"

    def test_links_to_closed_screens_are_hidden_from_him_only(
        self, client_as, school, seeded_calendar, klass, supervisor, principal_user
    ):
        url = reverse("student_affairs:dashboard")
        add = reverse("student_affairs:student_add")
        transfers = reverse("student_affairs:transfer_list")

        mine = client_as(supervisor).get(url).content.decode()
        assert add not in mine and transfers not in mine
        assert reverse("student_affairs:student_list") in mine

        theirs = client_as(principal_user).get(url).content.decode()
        assert add in theirs and transfers in theirs


# ══════════════════════════════════════════════════════════════════════
#  4. سجلُّ الطلبة — جناحُه قبل كلّ مرشِّح
# ══════════════════════════════════════════════════════════════════════


class TestTheRegisterIsHisWing:
    @pytest.fixture
    def unenrolled(self, school):
        user = UserFactory(full_name="طالب بلا قيد", national_id="29400000055")
        MembershipFactory(user=user, school=school, role=RoleFactory(school=school, name="student"))
        return user

    @pytest.mark.parametrize("query", ["", "?status=all", "?status=unenrolled", "?year=2020-2021"])
    def test_every_status_and_year_shows_only_his_wing(
        self,
        client_as,
        school,
        seeded_calendar,
        klass,
        supervisor,
        wing_kid,
        outsider,
        unenrolled,
        query,
    ):
        ctx = client_as(supervisor).get(reverse("student_affairs:student_list") + query).context

        assert [row["id"] for row in ctx["students"]] == [wing_kid.id]
        assert ctx["total"] == 1
        assert ctx["status"] == "enrolled"
        assert [code for code, _ in ctx["statuses"]] == ["enrolled"]

    def test_searching_another_wings_national_id_finds_nothing(
        self, client_as, school, seeded_calendar, klass, supervisor, wing_kid, outsider
    ):
        url = reverse("student_affairs:student_list") + f"?q={OUTSIDER_NID}"

        assert client_as(supervisor).get(url).context["total"] == 0

    def test_the_filters_and_the_htmx_table_are_his_wing(
        self, client_as, school, seeded_calendar, klass, supervisor, wing_kid, outsider
    ):
        client = client_as(supervisor)
        ctx = client.get(reverse("student_affairs:student_list")).context
        assert list(ctx["grades"]) == ["G7"]
        assert list(ctx["sections"]) == ["1"]

        partial = client.get(
            reverse("student_affairs:student_list") + "?grade=G8", HTTP_HX_REQUEST="true"
        )
        assert partial.context["total"] == 0
        assert outsider.full_name not in partial.content.decode()

    def test_the_rows_carry_no_edit_button_for_him(
        self, client_as, school, seeded_calendar, klass, supervisor, principal_user, wing_kid
    ):
        url = reverse("student_affairs:student_list")
        edit = reverse("student_affairs:student_edit", args=[wing_kid.id])
        export = reverse("student_affairs:student_export")

        mine = client_as(supervisor).get(url).content.decode()
        assert edit not in mine and export not in mine

        theirs = client_as(principal_user).get(url).content.decode()
        assert edit in theirs and export in theirs

    def test_leadership_keeps_the_whole_register_and_the_year(
        self,
        client_as,
        school,
        seeded_calendar,
        klass,
        principal_user,
        wing_kid,
        outsider,
        unenrolled,
    ):
        client = client_as(principal_user)
        url = reverse("student_affairs:student_list")

        assert client.get(url).context["total"] == 2
        assert client.get(url + "?status=all").context["total"] == 3
        assert client.get(url + "?year=2020-2021").context["year"] == "2020-2021"


# ══════════════════════════════════════════════════════════════════════
#  5. ملفُّ الطالب — ما يُحجب عنه وإن كان الطالبُ من جناحه
# ══════════════════════════════════════════════════════════════════════

HIDDEN_TABLES = (
    "assessments_annualsubjectresult",
    "core_healthrecord",
    "core_bookborrowing",
    "student_affairs_studentactivity",
    "student_affairs_studenttransfer",
)


class TestTheProfileHidesWhatIsNotHis:
    @pytest.fixture
    def health(self, school, wing_kid):
        HealthRecordFactory(student=wing_kid, blood_type="AB-")
        ClinicVisitFactory(school=school, student=wing_kid, reason="سببٌ طبّيٌّ خاصّ", is_sent_home=True)

    def test_the_hidden_sections_are_not_even_queried(
        self, client_as, school, seeded_calendar, klass, supervisor, wing_kid, health
    ):
        client = client_as(supervisor)
        url = reverse("student_affairs:student_profile", args=[wing_kid.id])
        client.get(url)  # إحماء

        with CaptureQueriesContext(connection) as captured:
            response = client.get(url)

        touched = [
            t for t in HIDDEN_TABLES if any(t in q["sql"] for q in captured.captured_queries)
        ]
        assert response.status_code == 200
        assert touched == [], f"قُرئ ما يُحجب: {touched}"
        ctx = response.context
        assert ctx["limited"] is True
        assert not ctx["grades"] and ctx["health_record"] is None
        assert (ctx["borrowings"], ctx["activities"], ctx["transfers"]) == ([], [], [])

    def test_the_clinic_shows_the_date_and_sent_home_only(
        self, client_as, school, seeded_calendar, klass, supervisor, wing_kid, health
    ):
        response = client_as(supervisor).get(
            reverse("student_affairs:student_profile", args=[wing_kid.id])
        )
        body = response.content.decode()

        assert "سببٌ طبّيٌّ خاصّ" not in body
        assert "AB-" not in body and "فصيلة الدم" not in body
        assert "أُرسل للمنزل" in body
        assert set(response.context["clinic_visits"][0]) == {"visit_date", "is_sent_home"}

    def test_buttons_to_screens_he_cannot_open_are_hidden(
        self, client_as, school, seeded_calendar, klass, supervisor, wing_kid
    ):
        body = (
            client_as(supervisor)
            .get(reverse("student_affairs:student_profile", args=[wing_kid.id]))
            .content.decode()
        )

        assert reverse("student_affairs:student_edit", args=[wing_kid.id]) not in body
        assert reverse("student_result_pdf", args=[wing_kid.id]) not in body
        assert reverse("behavior:summon_parent_student", args=[wing_kid.id]) not in body
        assert 'data-tab="grades"' not in body and 'data-tab="activities"' not in body
        assert reverse("student_affairs:student_profile_pdf", args=[wing_kid.id]) in body

    def test_leadership_sees_the_whole_file(
        self, client_as, school, seeded_calendar, klass, principal_user, wing_kid, health
    ):
        response = client_as(principal_user).get(
            reverse("student_affairs:student_profile", args=[wing_kid.id]) + "?year=2020-2021"
        )
        body = response.content.decode()

        assert response.context["limited"] is False
        assert response.context["year"] == "2020-2021"
        assert "سببٌ طبّيٌّ خاصّ" in body and "AB-" in body
        assert 'data-tab="grades"' in body
        assert reverse("student_affairs:student_edit", args=[wing_kid.id]) in body


# ══════════════════════════════════════════════════════════════════════
#  6. نسخةُ PDF — مستورةُ الرقم بلا درجات، والأثرُ يقول ذلك
# ══════════════════════════════════════════════════════════════════════


class TestTheProfilePdf:
    def _render(self, client, student):
        with patch(
            "student_affairs.views.render_pdf", return_value=HttpResponse(b"%PDF")
        ) as rendered:
            response = client.get(reverse("student_affairs:student_profile_pdf", args=[student.id]))
        assert response.status_code == 200
        return rendered.call_args.args[0]

    def _logged(self, student):
        entry = AuditLog.objects.filter(action="export", object_id=str(student.pk)).latest(
            "timestamp"
        )
        return entry.changes["full_national_id"]

    def test_the_supervisor_prints_the_full_number_without_grades(
        self, client_as, school, seeded_calendar, klass, supervisor, wing_kid
    ):
        """الوثيقةُ الفرديّةُ تحمل الرقمَ كاملاً للجميع، ويُسجَّل ذلك في التدقيق."""
        html = self._render(client_as(supervisor), wing_kid)

        assert wing_kid.national_id in html
        assert "الدرجات الحالية" not in html
        assert self._logged(wing_kid) is True

    def test_leadership_keeps_the_full_number(
        self, client_as, school, seeded_calendar, klass, principal_user, wing_kid
    ):
        html = self._render(client_as(principal_user), wing_kid)

        assert wing_kid.national_id in html
        assert self._logged(wing_kid) is True

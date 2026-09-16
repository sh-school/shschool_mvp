"""وحدةُ السلوك لمشرف الجناح — طلبةُ جناحه وحدَهم (قرارا 2026-09-14/15).

كان `get_teacher_student_ids` يُعيد للمشرف الإداريّ `None` — «كلّ الطلاب» — فتعرض له لوحةُ
السلوك مخالفاتِ المدرسة، ويفتح ملفَّ أيّ طالبٍ وتقريرَه ونسخةَ PDF منه، ويسرد نموذجُ المخالفة
أسماءَ المدرسة كلِّها ويقبل أيَّ معرّف. والقرارُ:

- يرى طلبةَ شُعب أجنحته ومخالفاتِهم أيّاً كان راصدُها، ويرصد عليهم.
- معرّفُ طالبٍ خارج جناحه — في الرابط أو الاستعلام أو النموذج — يعود 404 ولا يُكتب شيء.
- ولا يوسّع `?year=` نطاقَه.
- والقيادةُ والمعلّمون على ما كانوا حرفاً: المديرُ للمدرسة، والمعلّمُ لطلبة جدوله بصفحة المنع،
  ويرصد المعلّمُ كما كان.
"""

from unittest import mock

import pytest
from django.http import HttpResponse
from django.urls import reverse

from core.models import BehaviorInfraction, Wing
from core.permissions import get_teacher_student_ids
from tests.conftest import (
    BehaviorInfractionFactory,
    ClassGroupFactory,
    MembershipFactory,
    RoleFactory,
    StudentEnrollmentFactory,
    UserFactory,
)
from tests.test_period_register import klass, supervisor, teacher, year  # noqa: F401

pytestmark = pytest.mark.django_db


def _staff(school, name, role):
    user = UserFactory(full_name=name)
    MembershipFactory(user=user, school=school, role=RoleFactory(school=school, name=role))
    return user


def _student(school, group, name):
    user = UserFactory(full_name=name)
    MembershipFactory(user=user, school=school, role=RoleFactory(school=school, name="student"))
    StudentEnrollmentFactory(student=user, class_group=group)
    return user


@pytest.fixture
def far_klass(school, seeded_calendar, year):
    """شعبةٌ في جناحٍ ثانٍ — ليست من شُعب المشرف."""
    wing = Wing.objects.create(school=school, code="w2", name="جناح 2", academic_year=year)
    return ClassGroupFactory(
        school=school, grade="G8", section="2", level_type="prep", academic_year=year, wing=wing
    )


@pytest.fixture
def mine(school, seeded_calendar, klass, supervisor):
    return _student(school, klass, "طالبُ جناحي")


@pytest.fixture
def theirs(school, seeded_calendar, far_klass):
    return _student(school, far_klass, "طالبُ الجناح الآخر")


@pytest.fixture
def principal(school):
    return _staff(school, "مدير المدرسة", "principal")


def _record_payload(student):
    return {
        "student_id": str(student.id),
        "level": 1,
        "description": "إزعاجٌ في الممرّ",
        "disciplinary_action_type": "verbal_warning",
    }


# ── الدالّة المركزيّة ─────────────────────────────────────────────


class TestTheVisibleStudents:
    def test_the_supervisor_gets_his_wing_not_the_school(
        self, school, seeded_calendar, mine, theirs, supervisor
    ):
        assert get_teacher_student_ids(supervisor) == {mine.id}

    def test_leadership_still_sees_everyone_without_a_query(
        self, school, seeded_calendar, principal, django_assert_num_queries
    ):
        vice_admin = _staff(school, "النائب الإداريّ", "vice_admin")
        for user in (principal, vice_admin):
            user.get_role()  # العضويّةُ الحاكمةُ محمَّلةٌ سلفاً كما في الطلب
            with django_assert_num_queries(0):
                assert get_teacher_student_ids(user) is None

    def test_a_supervisor_without_a_wing_sees_no_one(self, school, seeded_calendar, theirs):
        lonely = _staff(school, "مشرفٌ بلا جناح", "admin_supervisor")
        assert get_teacher_student_ids(lonely) == set()


# ── لوحةُ السلوك ─────────────────────────────────────────────────


class TestTheDashboard:
    def test_it_counts_only_his_wing_whoever_reported(
        self, client_as, school, seeded_calendar, mine, theirs, supervisor, teacher
    ):
        BehaviorInfractionFactory(school=school, student=mine, reported_by=teacher, level=3)
        BehaviorInfractionFactory(school=school, student=theirs, reported_by=teacher, level=3)
        BehaviorInfractionFactory(school=school, student=theirs, reported_by=supervisor, level=1)

        ctx = client_as(supervisor).get(reverse("behavior:dashboard")).context

        assert {i.student_id for i in ctx["recent_infractions"]} == {mine.id}
        assert [i.student_id for i in ctx["critical_unresolved"]] == [mine.id]
        assert ctx["year_total"] == 1

    def test_the_principal_still_counts_the_school(
        self, client_as, school, seeded_calendar, mine, theirs, principal, teacher
    ):
        BehaviorInfractionFactory(school=school, student=mine, reported_by=teacher)
        BehaviorInfractionFactory(school=school, student=theirs, reported_by=teacher)

        ctx = client_as(principal).get(reverse("behavior:dashboard")).context

        assert {i.student_id for i in ctx["recent_infractions"]} == {mine.id, theirs.id}
        assert ctx["year_total"] == 2


# ── الرصد ────────────────────────────────────────────────────────


class TestRecording:
    def test_the_form_lists_his_wing_only(
        self, client_as, school, seeded_calendar, mine, theirs, supervisor
    ):
        resp = client_as(supervisor).get(reverse("behavior:report_infraction"))

        assert list(resp.context["students"]) == [mine]
        assert theirs.full_name not in resp.content.decode()

    def test_he_records_on_his_wing(self, client_as, school, seeded_calendar, mine, supervisor):
        resp = client_as(supervisor).post(
            reverse("behavior:report_infraction"), _record_payload(mine)
        )

        assert resp.status_code == 302
        assert BehaviorInfraction.objects.filter(student=mine, reported_by=supervisor).exists()

    def test_a_student_of_another_wing_is_404_and_nothing_is_written(
        self, client_as, school, seeded_calendar, theirs, supervisor
    ):
        client = client_as(supervisor)

        assert (
            client.post(reverse("behavior:report_infraction"), _record_payload(theirs)).status_code
            == 404
        )
        assert (
            client.post(
                reverse("behavior:quick_log"),
                {"student_id": str(theirs.id), "description": "x", "level": 1},
            ).status_code
            == 404
        )
        assert not BehaviorInfraction.objects.filter(student=theirs).exists()

    def test_quick_log_lists_and_accepts_his_wing_only(
        self, client_as, school, seeded_calendar, mine, theirs, supervisor
    ):
        client = client_as(supervisor)
        url = reverse("behavior:quick_log")

        assert list(client.get(url).context["students"]) == [mine]
        assert client.get(url, {"student_id": str(theirs.id)}).status_code == 404
        assert client.get(url, {"student_id": str(mine.id)}).status_code == 200

        client.post(url, {"student_id": str(mine.id), "description": "إزعاج", "level": 1})
        assert BehaviorInfraction.objects.filter(student=mine, reported_by=supervisor).exists()

    def test_the_teacher_still_records_as_before(
        self, client_as, school, seeded_calendar, theirs, teacher
    ):
        """قاعدةُ المعلّم لم تُمسّ: نموذجُ الرصد لم يكن يسأل عن جدوله، ولا يسأل الآن."""
        resp = client_as(teacher).post(
            reverse("behavior:report_infraction"), _record_payload(theirs)
        )

        assert resp.status_code == 302
        assert BehaviorInfraction.objects.filter(student=theirs, reported_by=teacher).exists()


# ── الملفُّ والتقريرُ ونسختُه ─────────────────────────────────────


class TestTheStudentPages:
    @pytest.mark.parametrize(
        "name",
        ["behavior:student_profile", "behavior:behavior_report", "behavior:student_behavior_pdf"],
    )
    def test_another_wings_student_is_404(
        self, client_as, school, seeded_calendar, theirs, supervisor, name
    ):
        url = reverse(name, kwargs={"student_id": theirs.id})
        assert client_as(supervisor).get(url, {"year": "2020-2021"}).status_code == 404

    def test_sending_the_report_of_another_wings_student_is_404(
        self, client_as, school, seeded_calendar, theirs, supervisor
    ):
        url = reverse("behavior:behavior_report", kwargs={"student_id": theirs.id})
        with mock.patch("notifications.services.NotificationService.send_email") as send:
            assert client_as(supervisor).post(url, {"action": "send"}).status_code == 404
        send.assert_not_called()

    def test_his_students_profile_shows_what_any_teacher_reported(
        self, client_as, school, seeded_calendar, mine, supervisor, teacher
    ):
        BehaviorInfractionFactory(school=school, student=mine, reported_by=teacher)

        resp = client_as(supervisor).get(
            reverse("behavior:student_profile", kwargs={"student_id": mine.id})
        )

        assert resp.status_code == 200
        assert [i.reported_by for i in resp.context["infractions"]] == [teacher]
        # نماذجُ الإنذار والتعهّد لإدارة المخالفات — لا تُعرض لمن تُغلق دونه.
        assert not resp.context["can_print_forms"]
        assert "pdf/warning" not in resp.content.decode()

    def test_the_report_year_does_not_widen_for_him(
        self, client_as, school, seeded_calendar, mine, supervisor, year
    ):
        client = client_as(supervisor)
        report = client.get(
            reverse("behavior:behavior_report", kwargs={"student_id": mine.id}),
            {"year": "2020-2021"},
        )
        assert report.context["year"] == year

        with mock.patch(
            "core.pdf_utils.render_pdf", return_value=HttpResponse(b"%PDF")
        ) as render_pdf:
            pdf = client.get(
                reverse("behavior:student_behavior_pdf", kwargs={"student_id": mine.id}),
                {"year": "2020-2021"},
            )
        assert pdf.status_code == 200
        assert render_pdf.call_args.args[1].endswith(f"_{year}.pdf")

    def test_the_principal_keeps_the_school_and_the_year_he_asks(
        self, client_as, school, seeded_calendar, theirs, principal
    ):
        client = client_as(principal)

        profile = client.get(reverse("behavior:student_profile", kwargs={"student_id": theirs.id}))
        report = client.get(
            reverse("behavior:behavior_report", kwargs={"student_id": theirs.id}),
            {"year": "2020-2021"},
        )

        assert profile.status_code == 200
        assert profile.context["can_print_forms"]
        assert report.status_code == 200
        assert report.context["year"] == "2020-2021"

    def test_the_teacher_is_still_refused_with_the_forbidden_page(
        self, client_as, school, seeded_calendar, theirs, teacher
    ):
        resp = client_as(teacher).get(
            reverse("behavior:student_profile", kwargs={"student_id": theirs.id})
        )
        assert resp.status_code == 403

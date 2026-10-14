"""استبانة تجربة المستخدم (W-20261015-002): الخصوصيّة بالبنية، الحجب بأعدادٍ حدّيّة، النافذة لكلّ دور، المراجعة."""

import datetime as dt

import pytest
from django.db import connection
from django.template import Context, Template
from django.test import RequestFactory
from django.urls import reverse
from django.utils import timezone

from core.models import AuditLog
from tests.conftest import MembershipFactory, RoleFactory, UserFactory
from ux_survey import services
from ux_survey.groups import group_of
from ux_survey.models import SurveyParticipation, SurveyResponse, SurveyWave

pytestmark = pytest.mark.django_db

SECRET = "تعذّر عليّ إيجاد كشف الغياب بسرعة"
ANSWER = {
    "usage_frequency": "daily",
    "usage_place": "school_pc",
    "sus_easy": "4",
    "sus_slow": "2",
    "sus_confident": "4",
    "sus_remember": "3",
    "find_fast": "often",
    "hardest_task": SECRET,
    "wish": "",
}
CARD = "أجيب الآن"


def _user(school, role, nid):
    user = UserFactory(full_name=f"مستخدم {role}", national_id=nid)
    MembershipFactory(user=user, school=school, role=RoleFactory(school=school, name=role))
    return user


@pytest.fixture
def wave(db):
    return SurveyWave.objects.create(name="الموجة الأولى", is_active=True)


def _answers(wave, group, count, review=0):
    for _ in range(count):
        SurveyResponse.objects.create(
            wave=wave,
            role_group=group,
            week=dt.date(2026, 10, 12),
            usage_frequency="daily",
            usage_place="phone",
            sus_easy=4,
            sus_slow=2,
            sus_confident=4,
            sus_remember=3,
            find_fast="often",
            hardest_task="نص",
            review=review,
        )


def _render_prompt(user, success=True):
    request = RequestFactory().get("/")
    request.user = user
    msgs = [type("M", (), {"level_tag": "success"})()] if success else []
    return Template("{% load ux_survey_tags %}{% survey_prompt %}").render(
        Context({"request": request, "messages": msgs})
    )


class TestStructurePrivacy:
    def test_the_response_table_has_no_link_to_a_person_or_exact_time(self):
        names = {f.name for f in SurveyResponse._meta.get_fields()}
        assert not names & {"user", "ip_address", "created_at", "session", "national_id"}
        related = {f.related_model for f in SurveyResponse._meta.get_fields() if f.is_relation}
        assert related <= {SurveyWave}
        assert not any(
            f.get_internal_type() == "DateTimeField" for f in SurveyResponse._meta.fields
        )

    def test_the_participation_table_holds_nothing_from_the_answer(self):
        names = {f.name for f in SurveyParticipation._meta.get_fields()}
        assert not names & {"hardest_task", "wish", "sus_easy", "role_group", "response"}
        fields = SurveyParticipation._meta.fields
        assert not any(f.get_internal_type() == "DateTimeField" for f in fields)
        related = {f.related_model for f in SurveyParticipation._meta.get_fields() if f.is_relation}
        assert SurveyResponse not in related

    def test_the_response_key_is_random_not_sequential(self, wave):
        _answers(wave, "teacher", 2)
        first, second = SurveyResponse.objects.all()
        assert len(str(first.pk)) == 36 and first.pk != second.pk

    def test_free_text_is_encrypted_at_rest_and_the_week_is_a_monday(self, client_as, school, wave):
        teacher = _user(school, "teacher", "29300001001")
        assert client_as(teacher).post(reverse("ux_survey:respond"), ANSWER).status_code == 302
        with connection.cursor() as cur:
            cur.execute("SELECT hardest_task FROM ux_survey_surveyresponse")
            raw = cur.fetchone()[0]
        assert SECRET not in raw
        row = SurveyResponse.objects.get()
        assert row.week.weekday() == 0 and row.role_group == "teacher"

    def test_answering_leaves_no_audit_row_naming_the_answerer(self, client_as, school, wave):
        teacher = _user(school, "teacher", "29300001002")
        client_as(teacher).post(reverse("ux_survey:respond"), ANSWER)
        pk = str(SurveyResponse.objects.get().pk)
        for row in AuditLog.objects.all():
            assert pk not in f"{row.object_id}{row.object_repr}{row.changes}"
            assert "SurveyResponse" not in f"{row.model_name}{row.object_repr}"


class TestGroups:
    def test_the_small_admin_roles_merge_into_one_group(self):
        for role in ("principal", "vice_admin", "vice_academic", "student_affairs_coordinator"):
            assert group_of(role) == "admin"
        assert group_of("teacher") == "teacher" and group_of("admin_supervisor") == "wing"

    def test_students_and_parents_have_no_group(self):
        assert group_of("student") is None and group_of("parent") is None and group_of(None) is None


class TestSuppression:
    def test_a_group_of_four_is_hidden_and_a_group_of_five_is_shown(self, wave):
        _answers(wave, "teacher", 9)
        _answers(wave, "wing", 5)
        _answers(wave, "support", 5)
        _answers(wave, "coordinator", 4)
        result = services.aggregate(wave)
        shown = {g["key"] for g in result["groups"]}
        assert "coordinator" not in shown and "teacher" in shown and result["total"] is None

    def test_one_hidden_group_also_hides_the_smallest_shown_so_subtraction_fails(self, wave):
        _answers(wave, "teacher", 9)
        _answers(wave, "coordinator", 5)
        _answers(wave, "wing", 4)
        result = services.aggregate(wave)
        assert [g["key"] for g in result["groups"]] == ["teacher"]
        assert result["hidden"] == 2 and result["total"] is None and result["overall"] is None

    def test_everything_shown_exposes_the_total(self, wave):
        _answers(wave, "teacher", 5)
        _answers(wave, "wing", 5)
        result = services.aggregate(wave)
        assert result["hidden"] == 0 and result["total"] == 10 and result["overall"]["n"] == 10

    def test_fewer_than_five_overall_shows_nothing(self, wave):
        _answers(wave, "teacher", 4)
        result = services.aggregate(wave)
        assert result["groups"] == [] and result["total"] is None


class TestPrompt:
    def test_a_teacher_sees_the_card_only_after_a_completed_task(self, school, wave):
        teacher = _user(school, "teacher", "29300001003")
        assert CARD in _render_prompt(teacher)
        assert CARD not in _render_prompt(teacher, success=False)

    @pytest.mark.parametrize("role", ["student", "parent"])
    def test_students_and_parents_never_see_it(self, school, wave, role):
        assert CARD not in _render_prompt(_user(school, role, "29300001004"))

    def test_no_card_without_an_open_wave(self, school):
        assert CARD not in _render_prompt(_user(school, "teacher", "29300001005"))

    def test_snooze_hides_it_for_seven_days_and_close_for_good(self, client_as, school, wave):
        teacher = _user(school, "teacher", "29300001006")
        client_as(teacher).post(reverse("ux_survey:snooze"))
        part = SurveyParticipation.objects.get()
        assert part.status == "snoozed"
        assert part.snooze_until == timezone.localdate() + dt.timedelta(days=7)
        assert CARD not in _render_prompt(teacher)
        part.snooze_until = timezone.localdate() - dt.timedelta(days=1)
        part.save()
        assert CARD in _render_prompt(teacher)
        client_as(teacher).post(reverse("ux_survey:close"))
        assert SurveyParticipation.objects.get().status == "closed"
        assert CARD not in _render_prompt(teacher)

    def test_it_never_returns_after_answering(self, client_as, school, wave):
        teacher = _user(school, "teacher", "29300001007")
        client_as(teacher).post(reverse("ux_survey:respond"), ANSWER)
        assert SurveyParticipation.objects.get().status == "answered"
        assert CARD not in _render_prompt(teacher)
        client_as(teacher).post(reverse("ux_survey:respond"), ANSWER)
        assert SurveyResponse.objects.count() == 1


class TestRespondView:
    @pytest.mark.parametrize("role", ["student", "parent"])
    def test_students_and_parents_are_denied(self, client_as, school, wave, role):
        user = _user(school, role, "29300001008")
        assert client_as(user).get(reverse("ux_survey:respond")).status_code in (302, 403)
        assert client_as(user).post(reverse("ux_survey:respond"), ANSWER).status_code in (302, 403)
        assert SurveyResponse.objects.count() == 0

    def test_staff_get_the_form_without_an_other_option(self, client_as, school, wave):
        user = _user(school, "teacher", "29300001009")
        body = client_as(user).get(reverse("ux_survey:respond")).content.decode()
        assert "ما المهمة الأصعب عليك الآن" in body and "آخر" not in body

    def test_free_text_over_two_hundred_is_rejected(self, client_as, school, wave):
        user = _user(school, "teacher", "29300001010")
        bad = {**ANSWER, "hardest_task": "أ" * 201}
        resp = client_as(user).post(reverse("ux_survey:respond"), bad)
        assert resp.status_code == 200 and SurveyResponse.objects.count() == 0


class TestDashboardAndReview:
    @pytest.mark.parametrize(
        ("role", "code", "nid"),
        [
            ("principal", 200, "29300002101"),
            ("platform_developer", 200, "29300002102"),
            ("teacher", 403, "29300002103"),
            ("vice_academic", 403, "29300002104"),
        ],
    )
    def test_only_principal_and_developer_open_the_dashboard(
        self, client_as, school, wave, role, code, nid
    ):
        user = _user(school, role, nid)
        assert client_as(user).get(reverse("ux_survey:dashboard")).status_code == code

    def test_the_principal_cannot_review(self, client_as, school, wave):
        principal = _user(school, "principal", "29300002001")
        assert client_as(principal).get(reverse("ux_survey:review")).status_code == 403

    def test_the_owner_review_audits_the_count_without_the_text(self, client_as, school, wave):
        _answers(wave, "teacher", 5)
        owner = _user(school, "platform_developer", "29300002002")
        pks = [str(p) for p in SurveyResponse.objects.values_list("pk", flat=True)]
        decisions = {"d_" + pks[0]: "1", "d_" + pks[1]: "2"}
        client_as(owner).post(reverse("ux_survey:review"), decisions)
        log = AuditLog.objects.filter(object_repr__contains="مراجعة نصوص").get()
        assert log.changes == {"count": 2}
        assert SurveyResponse.objects.filter(review=1).count() == 1

    def test_approved_text_shows_only_for_a_visible_group(self, wave):
        _answers(wave, "teacher", 6, review=1)
        _answers(wave, "support", 5, review=1)
        _answers(wave, "coordinator", 5, review=1)
        _answers(wave, "wing", 2, review=1)
        assert set(services.texts_for_dashboard(wave)) == {"معلم", "كادر الدعم"}


class TestRetentionAndAdmin:
    def test_purge_deletes_only_answers_older_than_twelve_months_and_is_idempotent(self, wave):
        today = dt.date(2026, 10, 15)
        _answers(wave, "teacher", 2)
        SurveyResponse.objects.update(week=today - dt.timedelta(days=366))
        _answers(wave, "wing", 1)
        SurveyResponse.objects.filter(role_group="wing").update(week=today - dt.timedelta(days=30))
        assert services.purge_old(today) == 2
        assert services.purge_old(today) == 0
        assert SurveyResponse.objects.count() == 1

    def test_the_admin_never_lists_the_free_text_fields(self):
        from django.contrib import admin

        model_admin = admin.site._registry[SurveyResponse]
        assert set(model_admin.exclude) == {"hardest_task", "wish"}
        assert not model_admin.has_add_permission(None)

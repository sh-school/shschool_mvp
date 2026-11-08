"""[LEGAL] تسجيلُ المخالفة بلا إجراء: اقتراحُ السلّم وتجهيزُ المشرف واعتمادُ المنسّق — W-20261108-007.

المصدر: AAdocs/ministry_data/2026_2027/08_conduct_policy_2026.md م3.5.3

الأرقامُ والعتباتُ تُقرأ من نصّ الملفّ نفسِه (لا من الذاكرة): جدولُ الدرجة الأولى المشترك (س316–321)
ومخالفةُ المظهر من الدرجة الثانية (س350–355). وما لم يُستخرج نصُّه لا يُقترح آليّاً.
"""

from pathlib import Path

import pytest
from django.core.exceptions import PermissionDenied
from django.urls import reverse

from behavior.action_proposal import POLICY_FILE, propose
from behavior.action_services import approve_action, approver_may_approve, prepare_action
from behavior.forms import InfractionForm
from behavior.models import BehaviorInfraction, ViolationCategory
from behavior.services import BehaviorService
from core.models import AuditLog
from tests.test_period_register import klass, supervisor, teacher, year  # noqa: F401
from tests.test_supervisor_behavior_scope import (  # noqa: F401
    _staff,
    far_klass,
    mine,
    principal,
    theirs,
)

pytestmark = pytest.mark.django_db

POLICY_LINES = (
    (Path(__file__).resolve().parents[1] / POLICY_FILE).read_text(encoding="utf-8").splitlines()
)


def _category(code="1-04", degree=1):
    return ViolationCategory.objects.get_or_create(
        code=code, defaults={"name_ar": "مخالفةٌ للاختبار", "degree": degree}
    )[0]


def _record(school, student, reporter, code="1-04", degree=1):
    return BehaviorService.create_infraction(
        school=school,
        student=student,
        reporter=reporter,
        level=degree,
        description="وصفٌ",
        violation_category=_category(code, degree),
    )


@pytest.fixture
def coordinator(school):
    return _staff(school, "منسّق شؤون الطلبة", "student_affairs_coordinator")


@pytest.fixture
def deputy(school):
    return _staff(school, "النائب الإداري", "vice_admin")


@pytest.fixture
def social(school):
    return _staff(school, "الأخصائي الاجتماعي", "social_worker")


# ── [LEGAL] السلّمُ من نصّ الملفّ ─────────────────────────────────────────


class TestTheLadderFollowsThePolicyText:
    @pytest.mark.parametrize("repetition", [1, 2, 3, 4, 5])
    def test_every_d1_step_sits_on_its_line_in_the_policy_file(self, repetition):
        """المصدر: 08_conduct_policy_2026.md م3.5.3 — كلُّ تكرارٍ يحمل سطرَه، وسطرُه في الملفّ هو هو."""
        found = propose("1-04", repetition)
        line = POLICY_LINES[int(found.source.rsplit(" س", 1)[1]) - 1]
        ordinal = ["الأولى", "الثانية", "الثالثة", "الرابعة", "الخامسة"][repetition - 1]
        assert f"المرة {ordinal}" in line
        assert found.source.startswith(f"{POLICY_FILE} م3.5.3 ص85–86 س")

    def test_the_specialist_thresholds_are_the_third_and_fifth_only(self):
        """س318 وس320 تنصّان على الاختصاصية الاجتماعية/النفسية؛ وغيرُهما لا."""
        flags = {n: propose("1-01", n).specialist for n in range(1, 6)}
        assert flags == {1: False, 2: False, 3: True, 4: False, 5: True}
        for number in (318, 320):
            assert "الاختصاصية الاجتماعية/النفسية" in POLICY_LINES[number - 1]

    def test_the_appearance_violation_refers_at_its_fifth_repetition(self):
        assert propose("2-01", 5).specialist is True
        assert "الاختصاصي الاجتماعي/النفسي" in POLICY_LINES[354 - 1]
        assert propose("2-01", 3).source.endswith("ص87–88 س352")

    @pytest.mark.parametrize(
        ("code", "repetition"),
        [("1-04", 6), ("1-04", 7), ("2-02", 1), ("2-05", 1), ("3-01", 1), ("4-05", 1)],
    )
    def test_what_the_file_does_not_extract_is_not_proposed(self, code, repetition):
        """السادسُ (فصلٌ واجتماعُ فريق) والدرجتان 3 و4 وبقيّةُ الثانية: لا اقتراحَ آليّ."""
        assert propose(code, repetition) is None


# ── تسجيلٌ بلا إجراء ─────────────────────────────────────────────────────


class TestRecordingWithoutAnAction:
    def test_the_form_accepts_a_violation_with_no_action(self):
        form = InfractionForm(
            {"student_id": "7d9f6d52-0d7c-4f67-a8bb-3a3f1d5d2c11", "level": 1}, role="teacher"
        )
        assert form.is_valid(), form.errors

    def test_the_view_records_it_and_stores_the_proposal(
        self, client_as, school, seeded_calendar, mine, principal
    ):
        payload = {
            "student_id": str(mine.id),
            "level": 1,
            "description": "إزعاجٌ في الممرّ",
            "violation_category": str(_category().id),
        }
        client_as(principal).post(reverse("behavior:report_infraction"), payload)
        saved = BehaviorInfraction.objects.get(student=mine)
        assert saved.disciplinary_action_type == ""
        assert saved.action_taken == ""
        assert (saved.proposed_rep, saved.approval_status) == (1, "pending")
        assert "م3.5.3" in saved.proposed_source

    def test_a_third_repetition_proposes_the_third_step_and_the_specialist_threshold(
        self, school, seeded_calendar, mine, principal
    ):
        for _ in range(2):
            _record(school, mine, principal)
        third = _record(school, mine, principal)
        assert third.proposed_rep == 3
        assert third.proposed_specialist is True

    def test_a_violation_with_no_extracted_ladder_is_recorded_without_a_proposal(
        self, school, seeded_calendar, mine, principal
    ):
        item = _record(school, mine, principal, code="3-01", degree=3)
        assert (item.proposed_text, item.approval_status) == ("", "")


# ── مشرفُ الجناح يجهّز ولا يستدعي ────────────────────────────────────────


class TestTheSupervisorPreparesOnly:
    def test_the_capability_is_his_and_summoning_is_not(self, supervisor, teacher):
        from core.capabilities import capability

        assert "admin_supervisor" in capability("behavior.prepare_action").roles
        assert "admin_supervisor" not in capability("behavior.summon_parent").roles
        assert "admin_supervisor" not in capability("behavior.manage").roles
        assert "teacher" not in capability("behavior.prepare_action").roles

    def test_he_prepares_a_pledge_for_a_student_of_his_wing(
        self, client_as, school, seeded_calendar, mine, supervisor, principal
    ):
        item = _record(school, mine, principal)
        response = client_as(supervisor).post(
            reverse("behavior:action_prepare", args=[item.id]), {"kind": "written_pledge"}
        )
        assert response.status_code == 302
        item.refresh_from_db()
        assert (item.prepared_kind, item.prepared_by_id) == ("written_pledge", supervisor.id)
        assert item.approval_status == "pending"
        assert item.parent_summoned is False

    def test_a_student_of_another_wing_is_a_404_and_nothing_is_written(
        self, client_as, school, seeded_calendar, theirs, supervisor, principal
    ):
        item = _record(school, theirs, principal)
        response = client_as(supervisor).post(
            reverse("behavior:action_prepare", args=[item.id]), {"kind": "referral"}
        )
        assert response.status_code == 404
        item.refresh_from_db()
        assert item.prepared_kind == ""

    def test_he_cannot_approve(
        self, client_as, school, seeded_calendar, mine, supervisor, principal
    ):
        item = _record(school, mine, principal)
        response = client_as(supervisor).post(
            reverse("behavior:action_approve", args=[item.id]), {"follow_up": "done"}
        )
        assert response.status_code == 403
        item.refresh_from_db()
        assert item.approval_status == "pending"


# ── اعتمادُ المنسّق وفصلُ المهامّ ─────────────────────────────────────────


class TestApprovalAndSeparationOfDuties:
    def test_the_coordinator_follows_up_and_approves_with_an_audit_row(
        self, client_as, school, seeded_calendar, mine, coordinator, principal
    ):
        item = _record(school, mine, principal)
        client_as(coordinator).post(
            reverse("behavior:action_approve", args=[item.id]), {"follow_up": "partial"}
        )
        item.refresh_from_db()
        assert (item.approval_status, item.follow_up) == ("approved", "partial")
        assert item.approved_by_id == coordinator.id
        # إشارةُ الحفظ العامّة تُدوّن صفوفَها أيضاً، فنختار صفَّ الاعتماد بوصفه
        row = AuditLog.objects.get(
            model_name="BehaviorInfraction",
            object_id=str(item.pk),
            object_repr__contains="اعتماد",
        )
        assert row.changes["follow_up"] == "partial"
        assert "م3.5.3" in row.changes["source"]
        assert item.action_taken == ""  # لا شيءَ يُكتب في حقل الأسرة

    @pytest.mark.parametrize("value", ["done", "not_done", "partial"])
    def test_the_three_follow_up_outcomes_are_accepted(
        self, school, seeded_calendar, mine, coordinator, principal, value
    ):
        item = approve_action(_record(school, mine, principal), coordinator, value)
        assert item.follow_up == value

    def test_a_coordinator_cannot_approve_what_he_recorded(
        self, school, seeded_calendar, mine, coordinator
    ):
        item = _record(school, mine, coordinator)
        assert approver_may_approve(coordinator, item) is False
        with pytest.raises(PermissionDenied):
            approve_action(item, coordinator, "done")

    def test_the_deputy_approves_what_the_coordinator_recorded_and_only_that(
        self, school, seeded_calendar, mine, coordinator, deputy, principal
    ):
        by_coordinator = _record(school, mine, coordinator)
        by_principal = _record(school, mine, principal)
        assert approver_may_approve(deputy, by_coordinator) is True
        assert approver_may_approve(deputy, by_principal) is False
        approve_action(by_coordinator, deputy, "done")
        assert by_coordinator.approved_by_id == deputy.id

    def test_a_specialist_does_not_approve(
        self, client_as, school, seeded_calendar, mine, social, principal
    ):
        item = _record(school, mine, principal)
        response = client_as(social).post(
            reverse("behavior:action_approve", args=[item.id]), {"follow_up": "done"}
        )
        assert response.status_code == 403

    def test_preparing_after_approval_is_refused(
        self, school, seeded_calendar, mine, coordinator, supervisor, principal
    ):
        item = approve_action(_record(school, mine, principal), coordinator, "done")
        with pytest.raises(PermissionDenied):
            prepare_action(item, supervisor, "referral")


# ── قائمةُ الاختصاصيّين ولا إشعارَ آليّ ──────────────────────────────────


class TestSpecialistsListAndNoAutomaticFamilyNotice:
    def test_the_referral_reaches_them_only_after_approval(
        self, client_as, school, seeded_calendar, mine, social, coordinator, principal
    ):
        for _ in range(2):
            _record(school, mine, principal)
        third = _record(school, mine, principal)
        url = reverse("behavior:referral_list")
        assert third.pk not in [i.pk for i in client_as(social).get(url).context["items"]]
        approve_action(third, coordinator, "done")
        assert third.pk in [i.pk for i in client_as(social).get(url).context["items"]]

    def test_the_coordinator_is_not_given_the_specialists_list(
        self, client_as, school, seeded_calendar, coordinator
    ):
        assert client_as(coordinator).get(reverse("behavior:referral_list")).status_code == 403

    def test_approving_does_not_summon_the_parent(
        self, school, seeded_calendar, mine, coordinator, principal
    ):
        item = approve_action(_record(school, mine, principal), coordinator, "done")
        assert (item.parent_summoned, item.parent_summon_date) == (False, None)

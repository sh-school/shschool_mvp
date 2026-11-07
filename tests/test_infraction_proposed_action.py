"""تسجيلُ المخالفة بلا إلزامٍ بالإجراء: اقتراحٌ من السلّم وتجهيزُ المشرف واعتمادُ المنسّق — W-20261108-005.

[LEGAL] اقتراحُ الإجراء ينقل خطواتِ السلّم ومصدرَها من نصّ الدليل لا من الذاكرة، والدرجتان 3 و4 بلا اقتراحٍ آليّ.
المصدر: AAdocs/ministry_data/2026_2027/08_conduct_policy_2026.md م3.5.3

القرارات (المالك 2026-11-08): تُسجَّل المخالفةُ بلا إجراء؛ مشرفُ الجناح يجهّز التعهّدَ الخطّيّ والإحالةَ لجناحه
وحدَه بلا استدعاء؛ المنسّقُ يتابع ويعتمد ومن سجّل لا يعتمد (النائبُ بديلُ المنسّق المسجِّل)؛ الاختصاصيّان
يدرسان ولا يعتمدان؛ لا إشعارَ آليّاً لوليّ الأمر من هذا المسار؛ ولا يصل الأسرةَ إجراءٌ قبل الاعتماد.
"""

from unittest import mock

import pytest
from django.core.exceptions import PermissionDenied
from django.urls import reverse

from behavior import action_services as flow
from behavior.action_proposal import propose
from behavior.models import BehaviorInfraction, ViolationCategory
from behavior.services import BehaviorService
from core.capabilities import has_capability
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

SOURCE = "AAdocs/ministry_data/2026_2027/08_conduct_policy_2026.md"


def _category(code: str, degree: int) -> ViolationCategory:
    return ViolationCategory.objects.get_or_create(
        code=code, defaults={"name_ar": f"بندٌ {code}", "degree": degree}
    )[0]


def _record(school, student, reporter, code="2-01", degree=2) -> BehaviorInfraction:
    return BehaviorService.create_infraction(
        school=school,
        student=student,
        reporter=reporter,
        level=degree,
        description="وصفٌ للمخالفة",
        violation_category=_category(code, degree),
    )


@pytest.fixture
def coordinator(school):
    return _staff(school, "منسّق شؤون الطلبة", "student_affairs_coordinator")


@pytest.fixture
def deputy(school):
    return _staff(school, "النائب الإداري", "vice_admin")


class TestTheProposalFollowsTheLadder:
    """[LEGAL] المصدر: 08_conduct_policy_2026.md م3.5.3 — الدرجة الأولى ص85–86 والثانية ص87–88."""

    def test_first_degree_first_repetition_is_the_verbal_warning_and_cites_the_page(self):
        proposal = propose("1-01", 1)
        assert proposal is not None
        assert "تنبيهٌ شفهيٌّ" in proposal.text
        assert SOURCE in proposal.source and "م3.5.3" in proposal.source
        assert "ص85–86" in proposal.source and "المرّة 1" in proposal.source

    def test_second_degree_third_repetition_is_the_guardians_pledge(self):
        proposal = propose("2-01", 3)
        assert proposal is not None
        assert "تعهّدٌ خطّيٌّ (1) من وليّ الأمر" in proposal.text
        assert "ص87–88" in proposal.source

    @pytest.mark.parametrize("code", ["3-01", "3-09", "4-05", "4-14"])
    def test_third_and_fourth_degrees_are_never_suggested(self, code):
        assert propose(code, 1) is None

    def test_past_the_end_of_the_ladder_nothing_is_guessed(self):
        assert propose("1-01", 7) is None

    def test_the_specialists_see_only_the_steps_the_policy_names_them_in(self):
        # الدرجة الأولى (ص85–86): المرّة الرابعة فيها «دراسة حالة» للاختصاصيّ الاجتماعيّ؛ والثالثةُ بلا اختصاصيّ.
        assert propose("1-01", 4).specialist is True
        assert propose("1-01", 3).specialist is False
        assert propose("1-01", 2).specialist is False
        # الدرجة الثانية (ص87–88): الرابعةُ للاجتماعيّ والخامسةُ للنفسيّ؛ والثالثةُ بلا اختصاصيّ.
        assert propose("2-01", 4).specialist is True
        assert propose("2-01", 5).specialist is True
        assert propose("2-01", 3).specialist is False


class TestRecordingWithoutAnAction:
    def test_an_infraction_is_saved_with_no_action_and_a_suggestion_is_computed(
        self, client_as, school, seeded_calendar, mine, principal
    ):
        category = _category("2-01", 2)
        payload = {
            "student_id": str(mine.id),
            "level": 2,
            "violation_category": str(category.id),
            "description": "مظهرٌ غيرُ لائق",
        }
        client_as(principal).post(reverse("behavior:report_infraction"), payload)
        saved = BehaviorInfraction.objects.get(student=mine)
        assert saved.disciplinary_action_type == ""
        assert saved.action_taken == ""  # ما تراه الأسرةُ فارغٌ قبل الاعتماد
        assert saved.suggested_action and saved.suggested_step == 1
        assert saved.approved_at is None

    def test_the_suggestion_is_audited(self, school, seeded_calendar, mine, teacher):
        infraction = _record(school, mine, teacher)
        row = AuditLog.objects.get(
            object_id=str(infraction.pk), user=teacher, changes__event="اقتراح الإجراء من السلّم"
        )
        assert row.changes["fields"]["suggested_action"]["before"] == ""
        assert row.changes["fields"]["suggested_action"]["after"] == infraction.suggested_action

    def test_a_third_degree_infraction_gets_no_suggestion(
        self, school, seeded_calendar, mine, teacher
    ):
        infraction = _record(school, mine, teacher, "3-01", 3)
        assert infraction.suggested_action == ""
        # لا اقتراحَ فلا سطرَ تدقيقٍ للاقتراح (قد تُدوّن تسجيلُ المخالفة نفسُه سطراً آخر).
        assert not AuditLog.objects.filter(
            object_id=str(infraction.pk), changes__event="اقتراح الإجراء من السلّم"
        ).exists()


class TestTheWingSupervisorPreparesForHisWingOnly:
    def test_the_capability_is_narrow(self, supervisor):
        assert has_capability(supervisor, "behavior.prepare_action")
        assert not has_capability(supervisor, "behavior.summon_parent")
        assert not has_capability(supervisor, "behavior.manage")
        assert not has_capability(supervisor, "behavior.approve_action")

    def test_prepares_a_pledge_for_a_student_of_his_wing(
        self, school, seeded_calendar, mine, teacher, supervisor
    ):
        infraction = _record(school, mine, teacher)
        flow.prepare_action(infraction, supervisor, "written_pledge")
        infraction.refresh_from_db()
        assert infraction.prepared_kind == "written_pledge"
        assert infraction.prepared_by == supervisor
        assert infraction.action_taken == ""  # التجهيزُ لا يصل الأسرة

    def test_refuses_a_student_of_another_wing(
        self, school, seeded_calendar, theirs, teacher, supervisor
    ):
        infraction = _record(school, theirs, teacher)
        with pytest.raises(PermissionDenied):
            flow.prepare_action(infraction, supervisor, "referral")
        assert not flow.prepare_queue(supervisor, school).filter(pk=infraction.pk).exists()

    def test_cannot_prepare_a_summons(self, school, seeded_calendar, mine, teacher, supervisor):
        infraction = _record(school, mine, teacher)
        with pytest.raises(ValueError):
            flow.prepare_action(infraction, supervisor, "parent_summons")

    def test_preparation_is_audited_with_before_and_after(
        self, school, seeded_calendar, mine, teacher, supervisor
    ):
        infraction = _record(school, mine, teacher)
        flow.prepare_action(infraction, supervisor, "referral")
        row = AuditLog.objects.get(user=supervisor, object_id=str(infraction.pk))
        assert row.changes["fields"]["prepared_kind"] == {"before": "", "after": "referral"}


class TestApprovalAndSeparationOfDuties:
    def test_the_coordinator_approves_a_teachers_infraction_and_the_family_field_is_filled(
        self, school, seeded_calendar, mine, teacher, coordinator
    ):
        infraction = _record(school, mine, teacher)
        flow.approve_action(infraction, coordinator)
        infraction.refresh_from_db()
        assert infraction.approved_by == coordinator and infraction.approved_at
        assert infraction.action_taken == infraction.suggested_action

    def test_approval_is_audited_with_before_and_after(
        self, school, seeded_calendar, mine, teacher, coordinator
    ):
        infraction = _record(school, mine, teacher)
        flow.approve_action(infraction, coordinator, "تنبيهٌ شفهيّ")
        row = AuditLog.objects.get(user=coordinator, object_id=str(infraction.pk))
        assert row.changes["event"] == "اعتماد الإجراء"
        assert row.changes["fields"]["action_taken"] == {"before": "", "after": "تنبيهٌ شفهيّ"}

    def test_a_coordinator_cannot_approve_what_he_recorded(
        self, school, seeded_calendar, mine, coordinator
    ):
        infraction = _record(school, mine, coordinator)
        with pytest.raises(PermissionDenied):
            flow.approve_action(infraction, coordinator)
        infraction.refresh_from_db()
        assert infraction.approved_at is None and infraction.action_taken == ""

    def test_the_deputy_approves_what_the_coordinator_recorded(
        self, school, seeded_calendar, mine, coordinator, deputy
    ):
        infraction = _record(school, mine, coordinator)
        assert flow.approval_queue(deputy, school).filter(pk=infraction.pk).exists()
        flow.approve_action(infraction, deputy)
        infraction.refresh_from_db()
        assert infraction.approved_by == deputy

    def test_the_deputy_does_not_approve_a_teachers_infraction(
        self, school, seeded_calendar, mine, teacher, deputy
    ):
        infraction = _record(school, mine, teacher)
        with pytest.raises(PermissionDenied):
            flow.approve_action(infraction, deputy)

    def test_the_coordinator_does_not_see_his_own_records_in_his_queue(
        self, school, seeded_calendar, mine, teacher, coordinator
    ):
        own = _record(school, mine, coordinator)
        theirs_ = _record(school, mine, teacher)
        queue = flow.approval_queue(coordinator, school)
        assert theirs_ in queue and own not in queue

    def test_a_third_degree_needs_the_coordinators_own_text(
        self, school, seeded_calendar, mine, teacher, coordinator
    ):
        infraction = _record(school, mine, teacher, "3-01", 3)
        with pytest.raises(ValueError):
            flow.approve_action(infraction, coordinator)
        flow.approve_action(infraction, coordinator, "إجراءٌ يكتبه المنسّق")
        infraction.refresh_from_db()
        assert infraction.action_taken == "إجراءٌ يكتبه المنسّق"

    def test_an_infraction_is_approved_once(
        self, school, seeded_calendar, mine, teacher, coordinator
    ):
        infraction = _record(school, mine, teacher)
        flow.approve_action(infraction, coordinator)
        with pytest.raises(ValueError):
            flow.approve_action(infraction, coordinator, "آخر")

    @pytest.mark.parametrize("status", ["done", "not_done", "partial"])
    def test_followup_records_who_and_is_audited(
        self, school, seeded_calendar, mine, teacher, coordinator, status
    ):
        infraction = _record(school, mine, teacher)
        flow.record_followup(infraction, coordinator, status)
        infraction.refresh_from_db()
        assert infraction.followup_status == status and infraction.followed_by == coordinator
        assert AuditLog.objects.filter(
            user=coordinator, object_id=str(infraction.pk), changes__event="متابعة الإجراء"
        ).exists()

    def test_an_unknown_followup_status_is_refused(
        self, school, seeded_calendar, mine, teacher, coordinator
    ):
        infraction = _record(school, mine, teacher)
        with pytest.raises(ValueError):
            flow.record_followup(infraction, coordinator, "x")


class TestSpecialistsStudyButDoNotApprove:
    def test_the_list_holds_referrals_at_the_policy_thresholds(
        self, school, seeded_calendar, mine, teacher
    ):
        social = _staff(school, "الأخصائي الاجتماعي", "social_worker")
        psych = _staff(school, "الأخصائي النفسي", "psychologist")
        first = _record(school, mine, teacher)  # المرّة الأولى: لا اختصاصيّ
        for _ in range(4):
            last = _record(school, mine, teacher)  # الخامسة: تنصّ على الاختصاصيّ الاجتماعيّ
        assert last.specialist_listed and not first.specialist_listed
        for user in (social, psych):
            queue = flow.specialist_queue(user, school)
            assert last in queue and first not in queue

    @pytest.mark.parametrize("role", ["social_worker", "psychologist"])
    def test_specialists_cannot_approve_or_follow_up(
        self, school, seeded_calendar, mine, teacher, role
    ):
        user = _staff(school, "اختصاصي", role)
        infraction = _record(school, mine, teacher)
        assert not has_capability(user, "behavior.approve_action")
        with pytest.raises(PermissionDenied):
            flow.approve_action(infraction, user)
        with pytest.raises(PermissionDenied):
            flow.record_followup(infraction, user, "done")

    def test_a_teacher_gets_no_specialist_list(self, school, teacher):
        assert not flow.specialist_queue(teacher, school).exists()


class TestNoAutomaticNoticeAndNothingVisibleToFamilies:
    def test_the_workflow_never_notifies_the_guardian(
        self, school, seeded_calendar, mine, teacher, coordinator, supervisor
    ):
        with mock.patch("behavior.views._notify_behavior_after_commit") as notify:
            infraction = _record(school, mine, teacher)
            flow.prepare_action(infraction, supervisor, "written_pledge")
            flow.record_followup(infraction, coordinator, "partial")
            flow.approve_action(infraction, coordinator)
        notify.assert_not_called()

    def test_nothing_reaches_the_family_field_before_approval(
        self, school, seeded_calendar, mine, teacher, coordinator, supervisor
    ):
        infraction = _record(school, mine, teacher)
        flow.prepare_action(infraction, supervisor, "referral")
        flow.record_followup(infraction, coordinator, "not_done")
        infraction.refresh_from_db()
        assert infraction.action_taken == "" and infraction.approved_at is None

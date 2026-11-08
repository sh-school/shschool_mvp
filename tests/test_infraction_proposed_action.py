"""اقتراحُ الإجراء من السلّم واعتمادُه — W-20261108-023 (طلب CA7E، قرارات المالك 2026-11-08).

[LEGAL] اقتراحُ الإجراء وعتباتُ الإحالة للاختصاصيّين منقولةٌ من نصّ الملفّ لا من الذاكرة:
المصدر: AAdocs/ministry_data/2026_2027/08_conduct_policy_2026.md م3.5.3
(الدرجة الأولى ص85–86 الأسطر 316–321، والدرجة الثانية «المظهر» ص87–88 الأسطر 350–355).
وما لم يُستخرج نصُّه (الدرجتان 3 و4 وبقيّةُ جداول الدرجة 2) لا يُقترح له شيءٌ آليّاً.
"""

import pytest
from django.core.exceptions import PermissionDenied
from django.urls import reverse

from behavior import action_selectors, action_services
from behavior.action_proposal import propose
from behavior.forms import InfractionForm
from behavior.models import BehaviorInfraction, ViolationCategory
from behavior.services import BehaviorService
from core.capabilities import has_capability
from core.models import AuditLog
from tests.test_period_register import klass, supervisor, teacher, year  # noqa: F401
from tests.test_supervisor_behavior_scope import (  # noqa: F401
    _staff,
    _student,
    far_klass,
    mine,
    principal,
    theirs,
)

pytestmark = pytest.mark.django_db

SOURCE_FILE = "08_conduct_policy_2026.md"


def _category(code, degree):
    category, _ = ViolationCategory.objects.get_or_create(
        code=code, defaults={"name_ar": f"مخالفة {code}", "degree": degree, "category": "A"}
    )
    return category


def _record(school, student, reporter, code="1-04", times=1):
    category = _category(code, int(code[0]))
    made = None
    for _ in range(times):
        made = BehaviorService.create_infraction(
            school=school,
            student=student,
            reporter=reporter,
            level=category.degree,
            description="إثارةُ فوضى في الممرّ",
            violation_category=category,
        )
    return made


@pytest.fixture
def coordinator(school):
    return _staff(school, "منسّق شؤون الطلبة", "student_affairs_coordinator")


@pytest.fixture
def vice_admin(school):
    return _staff(school, "النائب الإداريّ", "vice_admin")


@pytest.fixture
def social_worker(school):
    return _staff(school, "الأخصائيّ الاجتماعيّ", "social_worker")


class TestTheLadderProposal:
    @pytest.mark.parametrize(
        ("repetition", "action", "specialist", "line"),
        [
            (1, "verbal_warning", False, 316),
            (2, "verbal_warning", False, 317),
            (3, "social_specialist_referral", True, 318),
            (4, "written_pledge", False, 319),
            (5, "social_specialist_referral", True, 320),
        ],
    )
    def test_degree_one_follows_the_table_and_carries_the_article_and_line(
        self, repetition, action, specialist, line
    ):
        found = propose("1-04", repetition)
        assert (found.action_type, found.specialist) == (action, specialist)
        assert SOURCE_FILE in found.source
        assert "م3.5.3" in found.source
        assert found.source.endswith(f"سطر {line}")

    def test_the_sixth_repetition_and_beyond_stay_with_the_committee_path(self):
        assert propose("1-04", 6) is None
        assert propose("1-04", 9) is None

    def test_appearance_in_degree_two_is_transcribed_from_its_table(self):
        assert propose("2-01", 4).action_type == "parent_summons"
        assert propose("2-01", 5).specialist is True
        assert propose("2-01", 3).source.endswith("سطر 352")

    @pytest.mark.parametrize("code", ["2-02", "2-04", "3-01", "3-09", "4-05", "4-15", "9-99"])
    def test_what_the_file_does_not_extract_is_never_proposed(self, code):
        assert propose(code, 1) is None


class TestRecordingWithoutAnAction:
    def test_the_form_accepts_no_action(self):
        form = InfractionForm(
            {"student_id": "7d9f6d52-0d7c-4f67-a8bb-3a3f1d5d2c11", "level": 1}, role="teacher"
        )
        assert form.is_valid(), form.errors

    def test_the_view_records_it_and_keeps_the_family_visible_fields_empty(
        self, client_as, school, seeded_calendar, mine, principal
    ):
        category = _category("1-04", 1)
        payload = {
            "student_id": str(mine.id),
            "level": 1,
            "description": "إزعاجٌ في الممرّ",
            "violation_category": str(category.id),
        }
        client_as(principal).post(reverse("behavior:report_infraction"), payload)
        saved = BehaviorInfraction.objects.get(student=mine)
        assert saved.approval_status == "pending"
        assert saved.proposed_action_type == "verbal_warning"
        assert SOURCE_FILE in saved.proposed_source
        # ما يراه الأسرة لا يُكتب قبل الاعتماد
        assert saved.action_taken == ""
        assert saved.disciplinary_action_type == ""

    def test_an_unextracted_violation_is_recorded_with_no_proposal(
        self, school, seeded_calendar, mine, principal
    ):
        saved = _record(school, mine, principal, code="3-03")
        assert saved.approval_status == ""
        assert saved.proposed_action_type == ""

    def test_a_chosen_action_is_kept_as_it_was(self, school, seeded_calendar, mine, principal):
        saved = BehaviorService.create_infraction(
            school=school,
            student=mine,
            reporter=principal,
            level=1,
            description="وصف",
            violation_category=_category("1-04", 1),
            disciplinary_action_type="verbal_warning",
        )
        assert saved.approval_status == ""
        assert saved.disciplinary_action_type == "verbal_warning"

    def test_the_repetition_is_counted_per_violation(
        self, school, seeded_calendar, mine, principal
    ):
        saved = _record(school, mine, principal, times=3)
        assert saved.proposed_repetition == 3
        assert saved.proposed_specialist is True


class TestApprovalAndSeparationOfDuties:
    def test_the_coordinator_approves_a_teachers_record_and_it_is_audited(
        self, school, seeded_calendar, mine, teacher, coordinator
    ):
        row = _record(school, mine, teacher)
        action_services.approve(row, coordinator)
        row.refresh_from_db()
        assert row.approval_status == "approved"
        assert row.disciplinary_action_type == "verbal_warning"
        assert row.action_taken
        assert row.approved_by == coordinator
        entry = AuditLog.objects.get(object_id=str(row.pk), changes__event="action_approved")
        assert entry.user == coordinator
        assert entry.model_name == "BehaviorInfraction"

    def test_a_coordinator_who_recorded_cannot_approve_his_own(
        self, school, seeded_calendar, mine, coordinator, vice_admin
    ):
        row = _record(school, mine, coordinator)
        with pytest.raises(PermissionDenied):
            action_services.approve(row, coordinator)
        assert action_selectors.pending_for_approver(coordinator, school) == []
        assert [r.pk for r in action_selectors.pending_for_approver(vice_admin, school)] == [row.pk]
        action_services.approve(row, vice_admin)
        row.refresh_from_db()
        assert row.approved_by == vice_admin

    def test_the_vice_admin_does_not_approve_what_the_coordinator_can(
        self, school, seeded_calendar, mine, teacher, vice_admin
    ):
        row = _record(school, mine, teacher)
        with pytest.raises(PermissionDenied):
            action_services.approve(row, vice_admin)

    def test_the_specialist_cannot_approve(
        self, client_as, school, seeded_calendar, mine, teacher, social_worker
    ):
        row = _record(school, mine, teacher)
        response = client_as(social_worker).post(reverse("behavior:approve_action", args=[row.pk]))
        assert response.status_code == 403
        row.refresh_from_db()
        assert row.approval_status == "pending"

    def test_followup_takes_done_not_done_and_partial(
        self, school, seeded_calendar, mine, teacher, coordinator
    ):
        row = _record(school, mine, teacher)
        with pytest.raises(action_services.ActionError):
            action_services.record_followup(row, coordinator, "done")
        action_services.approve(row, coordinator)
        for status in ("done", "not_done", "partial"):
            action_services.record_followup(row, coordinator, status)
            row.refresh_from_db()
            assert row.followup_status == status
        with pytest.raises(action_services.ActionError):
            action_services.record_followup(row, coordinator, "anything")

    def test_approval_sends_nothing_to_the_guardian(
        self, school, seeded_calendar, mine, teacher, coordinator, monkeypatch
    ):
        from behavior import notify

        calls = []
        monkeypatch.setattr(notify, "notify_behavior_after_commit", lambda *a, **k: calls.append(1))
        row = _record(school, mine, teacher)
        action_services.approve(row, coordinator)
        assert calls == []


class TestTheWingSupervisorPreparation:
    def test_he_holds_the_narrow_capability_and_neither_summon_nor_manage(self, supervisor):
        assert has_capability(supervisor, "behavior.prepare_action")
        assert not has_capability(supervisor, "behavior.summon_parent")
        assert not has_capability(supervisor, "behavior.manage")
        assert not has_capability(supervisor, "behavior.approve_action")

    def test_he_prepares_a_pledge_for_his_own_wing(
        self, school, seeded_calendar, mine, teacher, supervisor
    ):
        row = _record(school, mine, teacher, times=4)
        assert row.proposed_action_type == "written_pledge"
        action_services.prepare(row, supervisor, "written_pledge")
        row.refresh_from_db()
        assert (row.prepared_kind, row.prepared_by) == ("written_pledge", supervisor)
        assert row.approval_status == "pending"  # التجهيزُ ليس اعتماداً
        assert AuditLog.objects.filter(
            object_id=str(row.pk), changes__event="action_prepared"
        ).exists()

    def test_he_cannot_prepare_for_another_wing(
        self, school, seeded_calendar, theirs, teacher, supervisor
    ):
        row = _record(school, theirs, teacher, times=4)
        with pytest.raises(PermissionDenied):
            action_services.prepare(row, supervisor, "written_pledge")
        assert action_selectors.pending_for_supervisor(supervisor, school) == []

    def test_the_kind_must_match_the_proposal(
        self, school, seeded_calendar, mine, teacher, supervisor
    ):
        row = _record(school, mine, teacher, times=4)
        with pytest.raises(action_services.ActionError):
            action_services.prepare(row, supervisor, "referral")

    def test_he_cannot_reach_the_approval_or_summon_screens(
        self, client_as, school, seeded_calendar, mine, teacher, supervisor
    ):
        row = _record(school, mine, teacher)
        client = client_as(supervisor)
        assert client.post(reverse("behavior:approve_action", args=[row.pk])).status_code == 403
        assert client.get(reverse("behavior:approval_queue")).status_code == 403
        assert client.get(reverse("behavior:summon_parent")).status_code == 403


class TestTheSpecialistList:
    def test_only_approved_threshold_referrals_reach_the_specialist(
        self, school, seeded_calendar, mine, teacher, coordinator, social_worker
    ):
        row = _record(school, mine, teacher, times=3)
        assert action_selectors.specialist_referrals(school) == []
        action_services.approve(row, coordinator)
        assert [r.pk for r in action_selectors.specialist_referrals(school)] == [row.pk]
        assert SOURCE_FILE in action_selectors.specialist_referrals(school)[0].proposed_source

    def test_the_specialist_opens_the_list(self, client_as, school, seeded_calendar, social_worker):
        response = client_as(social_worker).get(reverse("behavior:specialist_referrals"))
        assert response.status_code == 200

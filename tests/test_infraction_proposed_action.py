"""تسجيلُ المخالفة بلا إلزامٍ بالإجراء: اقتراحٌ من السلّم وتجهيزُ المشرف واعتمادُ المنسّق (W-20261112-003).

قراراتُ المالك 2026-11-08 (بلاغ CA7E): الاقتراحُ من سلّم الدليل بحسب الدرجة والتكرار؛ ومشرفُ الجناح يجهّز
لجناحه وحدَه ولا يستدعي؛ والمنسّقُ يعتمد ومن سجّل لا يعتمد؛ والاختصاصيّان يتلقّيان الإحالاتِ ولا يعتمدان؛
ولا إشعارَ آليَّ لوليّ الأمر؛ والدرجتان 3 و4 تبقيان في لجنة الضبط.
"""

import datetime as dt
from pathlib import Path

import pytest
from django.urls import reverse

from behavior import proposed_action as pa
from behavior.models import BehaviorInfraction, ViolationCategory
from core.academic_calendar import academic_year_for_school
from core.capabilities import capability
from core.models import AuditLog
from operations.models import ScheduleSlot
from tests.conftest import BehaviorInfractionFactory
from tests.test_behavior_edit import _staff, mine, theirs  # noqa: F401
from tests.test_period_register import klass, supervisor, teacher, year  # noqa: F401

pytestmark = pytest.mark.django_db

_MD = Path(__file__).resolve().parent.parent / pa.SOURCE_MD


@pytest.fixture
def category():
    # الرمز 1-01 مزروعٌ بهجرةٍ مسبقًا فلا يُنشأ ثانيةً (قيد الفرادة)
    return ViolationCategory.objects.get_or_create(
        code="1-01",
        defaults={"degree": 1, "name_ar": "مخالفة بسيطة", "category": "A"},
    )[0]


def _make(school, student, reporter, category=None, step=1, level=1, **over):
    return BehaviorInfractionFactory(
        school=school,
        student=student,
        reported_by=reporter,
        violation_category=category,
        escalation_step=step,
        level=level,
        description="وصف",
        disciplinary_action_type="",
        action_taken="",
        **over,
    )


def _url(name, infraction):
    return reverse(f"behavior:{name}", kwargs={"infraction_id": infraction.pk})


class TestLadderSuggestion:
    @pytest.mark.parametrize("key", list(pa.LADDER_TABLE))
    def test_every_threshold_is_copied_from_the_policy_line(self, key):
        """[LEGAL] كلُّ عتبةٍ في الجدول مطابقةٌ لسطرها في ملفّ السياسة.

        المصدر: AAdocs/ministry_data/2026_2027/08_conduct_policy_2026.md م3.5.3
        """
        lines = _MD.read_text(encoding="utf-8").splitlines()
        for repetition, (_, specialist, line_no, marker) in pa.LADDER_TABLE[key].items():
            assert marker in lines[line_no - 1], (key, repetition)
            if specialist:
                assert "الاجتماعي" in lines[line_no - 1] and "النفسي" in lines[line_no - 1]

    @pytest.mark.parametrize(
        ("degree", "code", "step", "action", "specialist"),
        [
            (1, "1-04", 1, "verbal_warning", False),
            (1, "1-04", 3, "social_specialist_referral", True),
            (1, "1-04", 4, "written_pledge", False),
            (1, "1-04", 5, "social_specialist_referral", True),
            (2, "2-01", 3, "written_pledge", False),
            (2, "2-01", 5, "social_specialist_referral", True),
        ],
    )
    def test_the_suggestion_follows_the_approved_ladder(
        self, degree, code, step, action, specialist
    ):
        """[LEGAL] الاقتراحُ يتبع سلّم المادة ويحمل رقمَها وسطرَ ملفّها.

        المصدر: AAdocs/ministry_data/2026_2027/08_conduct_policy_2026.md م3.5.3
        """
        proposal = pa.suggest(degree, code, step)
        assert (proposal.action, proposal.specialist) == (action, specialist)
        assert proposal.source.startswith("م3.5.3") and str(proposal.md_line) in proposal.source

    @pytest.mark.parametrize(
        ("degree", "code", "step"), [(1, "1-01", 6), (1, "1-01", 7), (2, "2-01", 6)]
    )
    def test_suspension_and_escalation_stay_with_the_committee(self, degree, code, step):
        assert pa.suggest(degree, code, step).action == ""

    @pytest.mark.parametrize(("degree", "code"), [(2, "2-02"), (3, "3-01"), (4, "4-05")])
    def test_what_the_source_does_not_extract_is_never_suggested(self, degree, code):
        proposal = pa.suggest(degree, code, 2)
        assert proposal.action == "" and proposal.reason == pa.NOT_EXTRACTED


class TestRecordingNeedsNoAction:
    def test_an_infraction_is_recorded_without_choosing_an_action(
        self,
        client_as,
        school,
        mine,
        teacher,
        category,  # noqa: F811
        klass,  # noqa: F811
    ):
        # المعلّم يسجّل على طلاب فصوله فقط: حصّةٌ في جدوله لصفّ الطالب (وإلا 404 موحَّد)
        ScheduleSlot.objects.create(
            school=school,
            teacher=teacher,
            class_group=klass,
            day_of_week=0,
            period_number=1,
            start_time=dt.time(7, 0),
            end_time=dt.time(7, 45),
            academic_year=academic_year_for_school(school),
        )
        resp = client_as(teacher).post(
            reverse("behavior:report_infraction"),
            {
                "student_id": str(mine.pk),
                "violation_category": str(category.pk),
                "description": "إثارة فوضى",
                "level": 1,
            },
        )
        assert resp.status_code == 302
        saved = BehaviorInfraction.objects.get(student=mine)
        assert (saved.disciplinary_action_type, saved.action_taken) == ("", "")
        assert saved.action_approved_at is None


class TestWingSupervisorPreparesOnly:
    def test_the_capability_is_narrow(self):
        assert capability("behavior.prepare_action").roles == frozenset({"admin_supervisor"})
        assert "admin_supervisor" not in capability("behavior.summon_parent").roles
        assert "admin_supervisor" not in capability("behavior.manage").roles
        assert "admin_supervisor" not in capability("behavior.approve_action").roles

    def test_prepares_a_pledge_for_his_own_wing_with_an_audit_trail(
        self,
        client_as,
        school,
        mine,
        teacher,
        supervisor,
        category,  # noqa: F811
    ):
        item = _make(school, mine, teacher, category)
        resp = client_as(supervisor).post(_url("prepare_action", item), {"kind": "written_pledge"})
        assert resp.status_code == 302
        item.refresh_from_db()
        assert (item.prepared_kind, item.prepared_by_id) == ("written_pledge", supervisor.pk)
        assert item.disciplinary_action_type == ""
        assert AuditLog.objects.filter(
            object_id=str(item.pk), object_repr__contains="تجهيز"
        ).exists()

    def test_another_wing_is_not_found(self, client_as, school, theirs, teacher, supervisor):  # noqa: F811
        item = _make(school, theirs, teacher)
        assert (
            client_as(supervisor)
            .post(_url("prepare_action", item), {"kind": "referral"})
            .status_code
            == 404
        )
        item.refresh_from_db()
        assert item.prepared_kind == ""

    def test_he_cannot_approve(self, client_as, school, mine, teacher, supervisor):  # noqa: F811
        item = _make(school, mine, teacher)
        resp = client_as(supervisor).post(
            _url("approve_action", item), {"action": "verbal_warning"}
        )
        assert resp.status_code == 403
        item.refresh_from_db()
        assert item.action_approved_at is None


class TestApproval:
    def test_the_coordinator_approves_and_it_is_audited(
        self,
        client_as,
        school,
        mine,
        teacher,
        category,  # noqa: F811
    ):
        item = _make(school, mine, teacher, category, step=3)
        coordinator = _staff(school, "student_affairs_coordinator")
        resp = client_as(coordinator).post(
            _url("approve_action", item), {"action": "written_pledge"}
        )
        assert resp.status_code == 302
        item.refresh_from_db()
        assert item.disciplinary_action_type == "written_pledge"
        assert item.action_taken == "تعهد خطي"
        assert item.action_approved_by_id == coordinator.pk and item.action_approved_at
        log = AuditLog.objects.get(object_id=str(item.pk), object_repr__contains="اعتماد")
        assert log.changes["approved_action"]["after"] == "written_pledge"
        assert log.user_id == coordinator.pk

    def test_a_coordinator_does_not_approve_his_own_infraction(
        self,
        client_as,
        school,
        mine,
        category,  # noqa: F811
    ):
        coordinator = _staff(school, "student_affairs_coordinator")
        item = _make(school, mine, coordinator, category)
        resp = client_as(coordinator).post(
            _url("approve_action", item), {"action": "verbal_warning"}
        )
        assert resp.status_code == 403
        item.refresh_from_db()
        assert item.action_approved_at is None and item.disciplinary_action_type == ""

    def test_the_deputy_approves_what_a_coordinator_recorded(
        self,
        client_as,
        school,
        mine,
        category,  # noqa: F811
    ):
        coordinator = _staff(school, "student_affairs_coordinator")
        item = _make(school, mine, coordinator, category)
        deputy = _staff(school, "vice_admin")
        resp = client_as(deputy).post(_url("approve_action", item), {"action": "verbal_warning"})
        assert resp.status_code == 302
        item.refresh_from_db()
        assert item.action_approved_by_id == deputy.pk

    def test_the_deputy_does_not_take_a_teachers_infraction(
        self,
        client_as,
        school,
        mine,
        teacher,
        category,  # noqa: F811
    ):
        item = _make(school, mine, teacher, category)
        deputy = _staff(school, "vice_admin")
        resp = client_as(deputy).post(_url("approve_action", item), {"action": "verbal_warning"})
        assert resp.status_code == 403
        item.refresh_from_db()
        assert item.action_approved_at is None

    @pytest.mark.parametrize("role", ["social_worker", "psychologist"])
    def test_the_specialists_do_not_approve(self, client_as, school, mine, teacher, category, role):  # noqa: F811
        item = _make(school, mine, teacher, category)
        resp = client_as(_staff(school, role)).post(
            _url("approve_action", item), {"action": "verbal_warning"}
        )
        assert resp.status_code == 403
        item.refresh_from_db()
        assert item.action_approved_at is None

    def test_followup_is_recorded_after_approval_only(
        self,
        client_as,
        school,
        mine,
        teacher,
        category,  # noqa: F811
    ):
        item = _make(school, mine, teacher, category)
        client = client_as(_staff(school, "student_affairs_coordinator"))
        client.post(_url("followup_action", item), {"result": "done"})
        item.refresh_from_db()
        assert item.action_followup == ""
        client.post(_url("approve_action", item), {"action": "verbal_warning"})
        client.post(_url("followup_action", item), {"result": "partial"})
        item.refresh_from_db()
        assert item.action_followup == "partial"


class TestQueues:
    def test_a_pending_row_shows_the_proposal_with_its_source_and_no_action_yet(
        self,
        client_as,
        school,
        mine,
        teacher,
        category,  # noqa: F811
    ):
        item = _make(school, mine, teacher, category, step=3)
        resp = client_as(_staff(school, "student_affairs_coordinator")).get(
            reverse("behavior:proposed_actions")
        )
        assert resp.status_code == 200
        [row] = resp.context["queues"].pending
        assert row.infraction.pk == item.pk and row.can_approve
        assert row.proposal.action == "social_specialist_referral"
        assert "م3.5.3" in resp.content.decode()
        assert item.action_taken == ""

    def test_degrees_three_and_four_stay_in_the_committee_path(
        self,
        client_as,
        school,
        mine,
        teacher,  # noqa: F811
    ):
        _make(school, mine, teacher, level=3)
        _make(school, mine, teacher, level=4)
        resp = client_as(_staff(school, "student_affairs_coordinator")).get(
            reverse("behavior:proposed_actions")
        )
        assert resp.context["queues"].pending == []

    def test_the_supervisor_sees_only_his_wing(
        self,
        client_as,
        school,
        mine,
        theirs,
        teacher,
        supervisor,  # noqa: F811
    ):
        _make(school, mine, teacher)
        _make(school, theirs, teacher)
        resp = client_as(supervisor).get(reverse("behavior:proposed_actions"))
        students = {row.infraction.student_id for row in resp.context["queues"].pending}
        assert students == {mine.pk}

    def test_specialists_receive_referrals_only_after_approval_at_the_policy_threshold(
        self,
        client_as,
        school,
        mine,
        teacher,
        category,  # noqa: F811
    ):
        at_threshold = _make(school, mine, teacher, category, step=3)
        _make(school, mine, teacher, category, step=2, date=at_threshold.date)
        specialist_user = _staff(school, "social_worker")
        url = reverse("behavior:proposed_actions")
        assert client_as(specialist_user).get(url).context["queues"].referrals == []
        client_as(_staff(school, "student_affairs_coordinator")).post(
            _url("approve_action", at_threshold), {"action": "social_specialist_referral"}
        )
        # `client_as` يعيد العميلَ نفسه: يُعاد دخولُ الاختصاصيّ بعد جلسة المنسّق
        referrals = client_as(specialist_user).get(url).context["queues"].referrals
        assert [r.infraction.pk for r in referrals] == [at_threshold.pk]

    def test_no_automatic_notice_goes_to_the_guardian_on_approval(
        self,
        client_as,
        school,
        mine,
        teacher,
        category,
        monkeypatch,  # noqa: F811
    ):
        import behavior.notify as notify

        sent = []
        for name in dir(notify):
            if name.startswith(("notify", "send")):
                monkeypatch.setattr(notify, name, lambda *a, **k: sent.append(1))
        item = _make(school, mine, teacher, category)
        client_as(_staff(school, "student_affairs_coordinator")).post(
            _url("approve_action", item), {"action": "parent_summons"}
        )
        item.refresh_from_db()
        assert sent == [] and item.parent_summoned is False

"""الإجراءُ المقترح من السلّم المعتمد: تسجيلٌ بلا إلزام، وتجهيزُ المشرف، واعتمادُ المنسّق (W-20261108-027).

[LEGAL] اقتراحُ الإجراء يتبع سلّمَ الدليل التنظيميّ بحسب الدرجة والتكرار وينقل رقمَ المادة وصفحتَها.
المصدر: AAdocs/ministry_data/2026_2027/08_conduct_policy_2026.md م3.5.3

[LEGAL] ما لم يُستخرج نصُّه (الدرجتان الثالثة والرابعة) لا يُقترح آليّاً.
المصدر: AAdocs/ministry_data/2026_2027/08_conduct_policy_2026.md م3.5.3

[LEGAL] الأخصائيّان لا يعتمدان؛ تصلهما الإحالاتُ عند العتبة التي ينصّ عليها السلّم.
المصدر: AAdocs/ministry_data/2026_2027/08_conduct_policy_2026.md م3.5.3
"""

import pytest
from django.urls import reverse

from behavior import proposed_action
from behavior.conduct_2026 import BY_CODE, PS, SW, SWPS
from behavior.forms import InfractionForm
from behavior.models import BehaviorInfraction, ViolationCategory
from core.capabilities import has_capability
from core.models import AuditLog
from tests.test_period_register import klass, supervisor, teacher, year  # noqa: F401
from tests.test_supervisor_behavior_scope import (  # noqa: F401
    _record_payload,
    _staff,
    far_klass,
    mine,
    principal,
    theirs,
)

pytestmark = [pytest.mark.django_db, pytest.mark.pin_clock]


def _category(code):
    item = BY_CODE[code]
    category, _ = ViolationCategory.objects.get_or_create(
        code=code, defaults={"degree": item.degree, "name_ar": item.name}
    )
    return category


def _pending(school, student, reporter, step=1, code="1-04"):
    """مخالفةٌ باقتراحها من السلّم عند التكرار `step` — كما تكتبها `create_infraction`."""
    category = _category(code)
    return BehaviorInfraction.objects.create(
        school=school,
        student=student,
        reported_by=reporter,
        violation_category=category,
        level=category.degree,
        escalation_step=step,
        description="وصفٌ",
        **proposed_action.proposal_fields(category, step),
    )


# ── [LEGAL] الاقتراحُ يتبع السلّم وينقل المادة ─────────────────────


@pytest.mark.parametrize("step", range(1, 7))
def test_the_proposal_is_the_ladder_row_with_its_article_and_page(step):
    """[LEGAL] السلّمُ المشترك للدرجة الأولى (ص85–86): الإجراءُ من صفّ التكرار نفسِه.

    المصدر: AAdocs/ministry_data/2026_2027/08_conduct_policy_2026.md م3.5.3
    """
    ladder = BY_CODE["1-04"].steps
    proposal = proposed_action.propose(_category("1-04"), step)
    rows = ladder.step(step)

    assert proposal is not None
    for actor, action in rows:
        assert f"{actor}: {action}" in proposal.text
    assert "م3.5.3" in proposal.basis
    assert f"ص{ladder.pages}" in proposal.basis
    assert f"التكرار {step}" in proposal.basis
    assert "08_conduct_policy_2026.md" in proposal.basis


def test_the_specialist_line_appears_exactly_where_the_ladder_names_a_specialist():
    """[LEGAL] سطرُ الإحالة للأخصائيّين حيث ينصّ السلّمُ عليه فقط.

    المصدر: AAdocs/ministry_data/2026_2027/08_conduct_policy_2026.md م3.5.3
    """
    ladder = BY_CODE["1-04"].steps
    named = {
        n
        for n in range(1, len(ladder.steps) + 1)
        if any(actor in {SW, PS, SWPS} for actor, _ in ladder.step(n))
    }

    assert named, "السلّمُ المشتركُ ينصّ على أخصائيٍّ في تكرارٍ واحدٍ على الأقلّ"
    for n in range(1, len(ladder.steps) + 1):
        line = proposed_action.propose(_category("1-04"), n).specialist_line
        assert bool(line) == (n in named)
        if line:
            assert line.startswith(f"م3.5.3 ص{ladder.pages} التكرار {n}:")


@pytest.mark.parametrize("code", ["3-01", "3-09", "4-05", "4-14"])
def test_degrees_three_and_four_are_never_proposed(code):
    """[LEGAL] ما لم يُستخرج نصُّه (الدرجتان 3 و4) لا يُقترح آليّاً.

    المصدر: AAdocs/ministry_data/2026_2027/08_conduct_policy_2026.md م3.5.3
    """
    assert proposed_action.propose(_category(code), 1) is None
    assert proposed_action.proposal_fields(_category(code), 1) == {}


def test_a_degree_two_infraction_gets_its_own_ladder_proposal():
    proposal = proposed_action.propose(_category("2-04"), 1)

    assert proposal is not None
    assert f"ص{BY_CODE['2-04'].steps.pages}" in proposal.basis


# ── التسجيلُ بلا إلزام بالإجراء ───────────────────────────────────


def test_the_form_no_longer_requires_an_action():
    form = InfractionForm(
        {"student_id": "7d9f6d52-0d7c-4f67-a8bb-3a3f1d5d2c11", "level": 1},
        role="teacher",
    )

    assert form.is_valid(), form.errors


def test_an_infraction_without_an_action_is_recorded_with_the_ladder_proposal(
    client_as, school, seeded_calendar, mine, principal
):
    category = _category("1-04")
    payload = _record_payload(mine)
    payload.pop("disciplinary_action_type")
    payload["violation_category"] = str(category.id)

    client_as(principal).post(reverse("behavior:report_infraction"), payload)

    saved = BehaviorInfraction.objects.get(student=mine)
    assert saved.disciplinary_action_type == ""
    assert saved.action_taken == ""
    assert saved.approval_status == "pending"
    assert "م3.5.3" in saved.proposed_basis
    assert saved.proposed_action


def test_a_degree_three_infraction_is_recorded_without_any_proposal(
    client_as, school, seeded_calendar, mine, principal
):
    payload = _record_payload(mine)
    payload.pop("disciplinary_action_type")
    payload["violation_category"] = str(_category("3-01").id)

    client_as(principal).post(reverse("behavior:report_infraction"), payload)

    saved = BehaviorInfraction.objects.get(student=mine)
    assert saved.proposed_action == ""
    assert saved.approval_status == ""


# ── مشرفُ الجناح: يجهّز لجناحه ولا يستدعي ─────────────────────────


def test_the_supervisor_prepares_a_pledge_for_a_student_of_his_wing(
    client_as, school, seeded_calendar, mine, supervisor, principal
):
    infraction = _pending(school, mine, principal)

    client_as(supervisor).post(
        reverse("behavior:prepare_proposals"),
        {"infraction_id": str(infraction.pk), "kind": "written_pledge"},
    )

    infraction.refresh_from_db()
    assert infraction.prepared_action == "written_pledge"
    assert infraction.prepared_by == supervisor
    assert infraction.approval_status == "pending"


def test_the_supervisor_cannot_prepare_for_another_wing(
    client_as, school, seeded_calendar, theirs, supervisor, principal
):
    infraction = _pending(school, theirs, principal)

    response = client_as(supervisor).post(
        reverse("behavior:prepare_proposals"),
        {"infraction_id": str(infraction.pk), "kind": "referral"},
    )

    assert response.status_code == 404
    infraction.refresh_from_db()
    assert infraction.prepared_action == ""


def test_the_supervisor_list_is_his_wing_only(
    client_as, school, seeded_calendar, mine, theirs, supervisor, principal
):
    _pending(school, mine, principal)
    _pending(school, theirs, principal)

    html = client_as(supervisor).get(reverse("behavior:prepare_proposals")).content.decode()

    assert mine.full_name in html
    assert theirs.full_name not in html


def test_the_supervisor_cannot_summon_manage_or_approve(
    client_as, school, seeded_calendar, mine, supervisor, principal
):
    infraction = _pending(school, mine, principal)

    assert has_capability(supervisor, "behavior.prepare_action")
    assert not has_capability(supervisor, "behavior.summon_parent")
    assert not has_capability(supervisor, "behavior.manage")
    assert not has_capability(supervisor, "behavior.approve_action")
    response = client_as(supervisor).post(
        reverse("behavior:approve_proposals"),
        {"infraction_id": str(infraction.pk), "follow_up": "done"},
    )
    assert response.status_code == 403
    with pytest.raises(ValueError):
        proposed_action.prepare(infraction, supervisor, "parent_summons")


# ── اعتمادُ المنسّق وفصلُ المهامّ وسجلُّ التدقيق ───────────────────


def test_the_coordinator_approves_with_a_follow_up_and_it_is_audited(
    client_as, school, seeded_calendar, mine, principal
):
    coordinator = _staff(school, "منسّق", "student_affairs_coordinator")
    teacher_user = _staff(school, "معلّم", "teacher")
    infraction = _pending(school, mine, teacher_user)

    client_as(coordinator).post(
        reverse("behavior:approve_proposals"),
        {"infraction_id": str(infraction.pk), "follow_up": "partial"},
    )

    infraction.refresh_from_db()
    assert infraction.approval_status == "approved"
    assert infraction.follow_up == "partial"
    assert infraction.approved_by == coordinator
    # إشارةُ الحفظ تكتب سجلَّها العامّ للمخالفة نفسها؛ فيُحصر الاستعلام بحدث الاعتماد
    entry = AuditLog.objects.get(
        model_name="BehaviorInfraction",
        object_id=str(infraction.pk),
        changes__event="approve_action",
    )
    assert entry.user == coordinator
    assert entry.changes["follow_up"] == "partial"


@pytest.mark.parametrize("follow_up", ["", "finished"])
def test_an_approval_needs_one_of_the_three_follow_ups(school, seeded_calendar, mine, follow_up):
    coordinator = _staff(school, "منسّق", "student_affairs_coordinator")
    infraction = _pending(school, mine, _staff(school, "معلّم", "teacher"))

    with pytest.raises(ValueError):
        proposed_action.approve(infraction, coordinator, follow_up)

    infraction.refresh_from_db()
    assert infraction.approval_status == "pending"


def test_a_coordinator_who_recorded_it_cannot_approve_it_himself(school, seeded_calendar, mine):
    coordinator = _staff(school, "منسّق", "student_affairs_coordinator")
    infraction = _pending(school, mine, coordinator)

    with pytest.raises(ValueError, match="لا يعتمد"):
        proposed_action.approve(infraction, coordinator, "done")


def test_another_coordinator_cannot_either_only_the_administrative_deputy(
    school, seeded_calendar, mine
):
    recorder = _staff(school, "منسّق ١", "student_affairs_coordinator")
    other = _staff(school, "منسّق ٢", "student_affairs_coordinator")
    deputy = _staff(school, "نائب إداريّ", "vice_admin")
    infraction = _pending(school, mine, recorder)

    with pytest.raises(ValueError, match="النائبُ الإداريّ"):
        proposed_action.approve(infraction, other, "done")
    proposed_action.approve(infraction, deputy, "not_done")

    infraction.refresh_from_db()
    assert infraction.approved_by == deputy
    assert infraction.follow_up == "not_done"


# ── الأخصائيّان: لا اعتمادَ، وقائمةُ إحالاتٍ بسطر السلّم ───────────


def test_the_specialists_get_a_referral_list_with_the_ladder_line_and_cannot_approve(
    client_as, school, seeded_calendar, mine, principal
):
    worker = _staff(school, "أخصائيّ اجتماعيّ", "social_worker")
    psychologist = _staff(school, "أخصائيّ نفسيّ", "psychologist")
    step = next(
        n for n in range(1, 7) if proposed_action.propose(_category("1-04"), n).specialist_line
    )
    infraction = _pending(school, mine, principal, step=step)
    quiet = _pending(school, mine, principal, step=1)

    for specialist in (worker, psychologist):
        assert not has_capability(specialist, "behavior.approve_action")
        html = client_as(specialist).get(reverse("behavior:referral_list")).content.decode()
        assert infraction.specialist_line in html
        assert quiet.proposed_action not in html
        assert (
            client_as(specialist)
            .post(
                reverse("behavior:approve_proposals"),
                {"infraction_id": str(infraction.pk), "follow_up": "done"},
            )
            .status_code
            == 403
        )


# ── لا إشعارَ لوليّ الأمر ولا ظهورَ للأسرة قبل الاعتماد ───────────


def test_proposal_fields_are_staff_only_and_leave_what_families_read_untouched(
    school, seeded_calendar, mine, principal
):
    infraction = _pending(school, mine, principal)

    assert infraction.proposed_action
    assert infraction.action_taken == ""
    assert infraction.disciplinary_action_type == ""
    assert infraction.approval_status == "pending"

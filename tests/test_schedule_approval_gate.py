"""[SCHEDULE] بوّابةُ الاعتماد (SCH-05) — لا جدولَ يُعتمد بمخالفةٍ صلبةٍ لم يُقَرّ بها.

اعتُمد جدولُ 2026-09-24 وفيه اثنتا عشرةَ مخالفةً لقاعدة التوزيع (HC6): حصّتا
رياضيات يومَ الأحد في 9/1 ولا شيءَ يومَ الخميس. كسرها المولّدُ برخصةٍ ولم يسدّدها،
والمختبرُ لخّصها في «98.2% مطابقة»، فلم يرها من اعتمد.

فالمدقّقُ يكتب ما بقي مكسوراً في `config_snapshot["breaches"]`، وهذه الاختبارات
تحرس ما بعده: الصفحةُ تسمّي المخالفاتِ بقيدها وشعبتها ومادّتها ويومها، والاعتمادُ
معها يلزمه إقرارٌ صريحٌ يُحكم فيه على الخادم — والمسودّةُ السليمةُ تُعتمد كما كانت.
"""

from types import SimpleNamespace

import pytest
from django.urls import reverse
from django.utils.html import escape

from operations.constraint_registry import REGISTRY
from operations.schedule_breaches import (
    BreachesNotAcknowledgedError,
    acknowledged,
    approval_refusal,
    draft_breaches,
)
from tests.conftest import ClassGroupFactory, MembershipFactory, RoleFactory, UserFactory

YEAR = "2026-2027"


def _item(code, *, day=0, period=6, cls="9/1", subject="الرياضيات", teacher="معلّمُ الرياضيات"):
    return {
        "code": code,
        "class": cls,
        "subject": subject,
        "teacher": teacher,
        "day": day,
        "period": period,
    }


def _snapshot(*items):
    """ما يكتبه `scheduler_audit.summary` في لقطة التوليد."""
    by_code: dict[str, int] = {}
    for item in items:
        by_code[item["code"]] = by_code.get(item["code"], 0) + 1
    return {"breaches": {"count": len(items), "by_code": by_code, "items": list(items)}}


# ── القراءةُ نفسُها: بلا قاعدة ────────────────────────────────────────


def test_breaches_are_grouped_in_registry_order_with_the_exemption_last():
    snapshot = _snapshot(
        _item("EX", day=4, period=1),
        _item("HC6", day=0, period=6),
        _item("HC5", day=2, period=3),
        _item("HC6", day=1, period=7, cls="9/2"),
    )

    view = draft_breaches(snapshot)

    assert view["count"] == 4
    assert [g["code"] for g in view["groups"]] == ["HC5", "HC6", "EX"]
    hc6 = view["groups"][1]
    assert hc6["title"] == REGISTRY["HC6"].title and hc6["count"] == 2
    rows = [row for col in hc6["cols"] for row in col]
    assert [(r["class"], r["day_name"]) for r in rows] == [("9/1", "الأحد"), ("9/2", "الاثنين")]
    assert view["groups"][2]["title"] == "تفريغ معلّم"


def test_a_generation_older_than_the_auditor_has_nothing_to_show():
    """غيابُ الشهادة ليس شهادةً بالمخالفة: لا عرضَ ولا حجب."""
    assert draft_breaches({}) is None
    assert draft_breaches(None) is None
    assert approval_refusal(SimpleNamespace(config_snapshot={}), False) == ""


@pytest.mark.parametrize(
    ("snapshot", "data", "refused"),
    [
        (_snapshot(_item("HC6")), {}, True),
        (_snapshot(_item("HC6")), {"acknowledge_breaches": ""}, True),
        (_snapshot(_item("HC6")), {"acknowledge_breaches": "1"}, False),
        (_snapshot(), {}, False),
    ],
)
def test_the_refusal_follows_the_count_and_the_acknowledgement(snapshot, data, refused):
    reason = approval_refusal(SimpleNamespace(config_snapshot=snapshot), acknowledged(data))

    assert bool(reason) is refused


# ── الصفحةُ والاعتماد ────────────────────────────────────────────────


@pytest.fixture
def principal(school):
    role = RoleFactory(school=school, name="principal")
    user = UserFactory(full_name="مدير المدرسة")
    MembershipFactory(user=user, school=school, role=role)
    return user


@pytest.fixture
def assignment(school):
    """الصفحةُ لا ترسم سجلَّ التوليد قبل أن يوجد توزيعٌ واحد."""
    from operations.models import Subject, SubjectClassAssignment

    role = RoleFactory(school=school, name="teacher")
    teacher = UserFactory(full_name="معلّمُ الرياضيات")
    MembershipFactory(user=teacher, school=school, role=role)
    subject = Subject.objects.create(school=school, name_ar="الرياضيات", code="MATH")
    group = ClassGroupFactory(school=school, grade="G9", level_type="prep", academic_year=YEAR)
    return SubjectClassAssignment.objects.create(
        school=school,
        academic_year=YEAR,
        teacher=teacher,
        class_group=group,
        subject=subject,
        weekly_periods=6,
        is_active=True,
    )


def _draft(school, snapshot):
    from operations.models import ScheduleGeneration

    return ScheduleGeneration.objects.create(
        school=school, academic_year=YEAR, status="draft", config_snapshot=snapshot
    )


def _approve(client, gen, **data):
    return client.post(reverse("approve_schedule", args=[gen.pk]), data, follow=True)


@pytest.mark.django_db
def test_the_page_names_each_breach_of_a_draft(client_as, principal, school, assignment):
    _draft(school, _snapshot(_item("HC6"), _item("EX", day=4, period=1)))

    body = client_as(principal).get(reverse("smart_schedule") + f"?year={YEAR}").content.decode()

    assert "HC6" in body and escape(REGISTRY["HC6"].title) in body
    assert "<b>9/1</b> · الرياضيات" in body and "الأحد، الحصّة 6" in body
    assert "تفريغ معلّم" in body
    assert 'name="acknowledge_breaches"' in body, "الإقرارُ حقلٌ في نموذج الاعتماد"


@pytest.mark.django_db
def test_a_draft_without_an_audit_shows_no_gate(client_as, principal, school, assignment):
    _draft(school, {})

    body = client_as(principal).get(reverse("smart_schedule") + f"?year={YEAR}").content.decode()

    assert "gen-breaches-" not in body
    assert 'name="acknowledge_breaches"' not in body


@pytest.mark.django_db
def test_approving_with_breaches_but_no_acknowledgement_is_refused(
    client_as, principal, school, assignment
):
    gen = _draft(school, _snapshot(_item("HC6")))

    response = _approve(client_as(principal), gen)

    gen.refresh_from_db()
    assert gen.status == "draft", "لا اعتمادَ بلا إقرار"
    assert "لم يُعتمد الجدول" in response.content.decode()


@pytest.mark.django_db
def test_acknowledging_the_breaches_approves(client_as, principal, school, assignment):
    gen = _draft(school, _snapshot(_item("HC6")))

    _approve(client_as(principal), gen, acknowledge_breaches="1")

    gen.refresh_from_db()
    assert gen.status == "approved"


@pytest.mark.django_db
@pytest.mark.parametrize("snapshot", [_snapshot(), {}], ids=["audited-clean", "before-auditor"])
def test_a_draft_without_breaches_approves_as_before(
    client_as, principal, school, assignment, snapshot
):
    gen = _draft(school, snapshot)

    _approve(client_as(principal), gen)

    gen.refresh_from_db()
    assert gen.status == "approved"


@pytest.mark.django_db
def test_the_service_itself_refuses_so_no_other_path_bypasses_the_gate(school):
    """أمرُ النقل والاستيرادُ يستدعيان الخدمةَ لا العرض — فالحارسُ فيها لا في الزرّ."""
    from operations.services import ScheduleService

    gen = _draft(school, _snapshot(_item("HC6")))

    with pytest.raises(BreachesNotAcknowledgedError):
        ScheduleService.approve_generation(gen, notify=False)

    gen.refresh_from_db()
    assert gen.status == "draft"
    assert ScheduleService.approve_generation(gen, notify=False, acknowledged=True)
    gen.refresh_from_db()
    assert gen.status == "approved"


# ── قُطع التوليدُ بنفاد الميزانية (0105، W-20261002-033) ────────────────────


@pytest.mark.django_db
def test_the_page_tells_who_approves_that_the_search_was_cut_short(
    client_as, principal, school, assignment
):
    snapshot = {"budget_cut": True, "budget_cut_attempt": 1, "budget_cut_after_s": 8}
    gen = _draft(school, snapshot)

    body = client_as(principal).get(reverse("smart_schedule") + f"?year={YEAR}").content.decode()

    assert f"gen-budget-cut-{gen.id}" in body
    assert "قُطع البحثُ بنفاد الميزانية" in body
    assert "المحاولة 1" in body and "بعد 8 ثانية" in body


@pytest.mark.django_db
def test_a_draft_not_cut_short_shows_no_cut_notice(client_as, principal, school, assignment):
    _draft(school, {"budget_cut": False})

    body = client_as(principal).get(reverse("smart_schedule") + f"?year={YEAR}").content.decode()

    assert "gen-budget-cut-" not in body


@pytest.mark.django_db
def test_a_cut_draft_with_breaches_is_still_refused_without_acknowledgement(
    client_as, principal, school, assignment
):
    """القطعُ لا يفتح بابَ اعتمادٍ بلا إقرار: المخالفاتُ الصلبةُ في اللقطة تبقى شرطَ الاعتماد."""
    gen = _draft(school, {**_snapshot(_item("HC6")), "budget_cut": True})

    response = _approve(client_as(principal), gen)

    gen.refresh_from_db()
    assert gen.status == "draft", "لم يُعتمد بلا إقرار"
    assert response.status_code == 200


# ── المتعذّراتُ شرطُ إقرارٍ كالمخالفات (OR-01، قرارُ المالك؛ W-20261002-033) ─────────


def _refusal(snapshot, ack=False):
    return approval_refusal(SimpleNamespace(config_snapshot=snapshot), ack)


def test_an_unplaced_task_alone_is_refused_until_acknowledged():
    reason = _refusal({"unplaced": 3})

    assert "3 مهمّةً متعذّرةً لم تجد موضعاً" in reason and "مخالفاتٌ" not in reason
    assert _refusal({"unplaced": 3}, ack=True) == ""


def test_breaches_and_unplaced_are_named_together():
    reason = _refusal({**_snapshot(_item("HC6")), "unplaced": 2})

    assert "مخالفاتٌ لقيودٍ صلبة (عددُها 1)" in reason and "2 مهمّةً متعذّرةً" in reason


def test_the_refusal_text_for_breaches_alone_is_unchanged():
    assert _refusal(_snapshot(_item("HC6"))) == (
        "لم يُعتمد الجدول: في المسودّة مخالفاتٌ لقيودٍ صلبة (عددُها 1). "
        "راجعها في سجلّ التوليد، ثمّ أقرَّ بها صراحةً عند الاعتماد."
    )


def test_the_refusal_says_the_search_was_cut_short_when_tasks_are_unplaced():
    assert "قُطع البحثُ بنفاد الميزانية" in _refusal({"unplaced": 1, "budget_cut": True})
    assert "قُطع البحثُ" not in _refusal({"unplaced": 1})
    assert _refusal({"budget_cut": True}) == "", "قطعٌ بلا متعذّراتٍ ولا مخالفات: لا حاجة لإقرار"


@pytest.mark.parametrize("recorded", [0, None, -2, True, "3", 1.5])
def test_a_snapshot_without_a_real_unplaced_count_is_never_refused(recorded):
    """لقطةٌ أقدمُ لا تحمله، وقيمٌ غير صالحة (صفرٌ، سالبٌ، منطقيٌّ، نصٌّ): لا رفضَ."""
    assert _refusal({"unplaced": recorded}) == ""


@pytest.mark.django_db
def test_the_service_refuses_an_unplaced_draft_without_acknowledgement(school):
    from operations.services import ScheduleService

    gen = _draft(school, {"unplaced": 2})

    with pytest.raises(BreachesNotAcknowledgedError):
        ScheduleService.approve_generation(gen, notify=False)

    gen.refresh_from_db()
    assert gen.status == "draft"
    assert ScheduleService.approve_generation(gen, notify=False, acknowledged=True)


@pytest.mark.django_db
def test_the_page_shows_the_gate_and_the_checkbox_for_an_unplaced_draft(
    client_as, principal, school, assignment
):
    gen = _draft(school, {"unplaced": 4, "budget_cut": True, "budget_cut_attempt": 1})

    body = client_as(principal).get(reverse("smart_schedule") + f"?year={YEAR}").content.decode()

    assert f"gen-breaches-{gen.id}" in body
    assert "<strong>4</strong>" in body and "مهمّةً متعذّرةً لم تجد موضعاً" in body
    assert 'name="acknowledge_breaches"' in body, "الإقرارُ حقلٌ في نموذج الاعتماد"
    assert "قُطع بحثُها بنفاد الميزانية" in body, "نافذةُ التأكيد تذكر القطع"
    assert "قُطع البحث" in body, "وسجلُّ التوليد يعلّم المسودّة"


@pytest.mark.django_db
def test_a_clean_draft_keeps_the_plain_approve_button(client_as, principal, school, assignment):
    _draft(school, {"unplaced": 0})

    body = client_as(principal).get(reverse("smart_schedule") + f"?year={YEAR}").content.decode()

    assert 'name="acknowledge_breaches"' not in body
    assert ">اعتماد</button>" in body

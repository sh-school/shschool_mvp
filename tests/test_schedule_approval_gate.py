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
from operations.schedule_breaches import approval_refusal, draft_breaches
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
    assert approval_refusal(SimpleNamespace(config_snapshot={}), {}) == ""


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
    reason = approval_refusal(SimpleNamespace(config_snapshot=snapshot), data)

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

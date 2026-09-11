"""[SCHEDULE] سجلُّ القيود ورتبةُ الكسر.

    الكودُ يعرّف، والقاعدةُ تستثني.

أخطرُ ما يُحرَس هنا أنّ **الافتراضَ لا يغيّر شيئاً**: السجلُّ يصف ما كان
يفعله المولّدُ قبله حرفاً بحرف، فمن لم يكتب صفَّ استثناءٍ لم يتبدّل جدولُه.
وأنّ **النواةَ لا تُحرَّر**: خرقُها يُنتج جدولاً مستحيلاً في الواقع لا
مزعجاً — معلّمٌ في غرفتين، أو معلّمٌ ينتقل طابقاً في صفر ثانية.

ورتبةُ الكسر نوعان: من يلين بنفسه يرفع سقفَه (التلاصقُ من واحدٍ إلى اثنين،
لا إلغاءً)، ومن لا سقفَ له يُتخطّى في تلك الجولة وحدَها.
"""

import pytest

from operations import constraint_registry as cr
from operations.models import ScheduleConstraintOverride
from operations.scheduler import ScheduleGrid, Task
from operations.scheduler_constraints import WEIGHTS, is_slot_valid

pytestmark = pytest.mark.django_db

YEAR = "2026-2027"


@pytest.fixture
def school(db):
    from core.models import School

    return School.objects.create(name="مدرسة الشحانية", code="SHH-REG")


def task(**kw):
    fields = {
        "class_id": "c1",
        "class_name": "c1",
        "subject_id": "s1",
        "subject_name": "الرياضيات",
        "subject_code": "MAT",
        "teacher_id": "t1",
        "teacher_name": "معلّم",
        "weekly_periods": 2,
        "level_type": "prep",
        "grade": "G8",
    }
    fields.update(kw)
    return Task(**fields)


def override(school, code, **kw):
    row = ScheduleConstraintOverride(
        school=school, academic_year=YEAR, code=code, reason="اختبار", **kw
    )
    row.full_clean()
    row.save()
    return row


# ── السجلُّ يصف ما هو قائم ───────────────────────────────────────────


def test_the_registry_weights_match_the_module_constants():
    """مصدرانِ لحقيقةٍ واحدةٍ يفترقان يوماً — فيُحرَس تطابقُهما اليوم.

    الأوزانُ تُقرأ من السياسة في `evaluate_soft_constraints`، وافتراضُها
    السجلّ. فلو خالف السجلُّ `WEIGHTS` تغيّر ترجيحُ المولّد صامتاً.
    """
    from_registry = {s.code: s.weight for s in cr.SOFT_CONSTRAINTS}

    assert from_registry == {k: float(v) for k, v in WEIGHTS.items()}


def test_the_core_is_not_tunable():
    """ستّةٌ لا تُحرَّر — وHC13 منها بقرار الإدارة 2026-09-10."""
    locked = {code for code, spec in cr.REGISTRY.items() if not spec.tunable}

    assert {"HC1", "HC2", "HC9", "HC12", "HC13", "HC19"} <= locked
    assert "HC10" in locked, "قرارٌ في حقّ الشخص يسبق كلّ رخصة"


def test_the_default_ranks_mirror_todays_generator():
    """الرخصةُ الأولى للتلاصق، والثانيةُ للتغطية والقسمة والتوزيع، وما عداها لا يُكسَر."""
    policy = cr.default_policy()

    assert policy.break_at("HC5") == cr.RELAXED
    assert policy.break_at("HC20") == cr.RELAXED, "تلاصقُ المادّة يُكسَر في الرخصة الأولى"
    assert {c for c in policy.breaks if policy.break_at(c) == cr.DENSE} == {
        "HC6",
        "HC14",
        "HC16B",
    }
    assert policy.break_at("HC17") == cr.NEVER


def test_a_licence_of_the_second_round_carries_the_first():
    policy = cr.default_policy()

    assert policy.licence("HC5", allow_adjacent=False, allow_dense=False) is False
    assert policy.licence("HC5", allow_adjacent=True, allow_dense=False) is True
    assert policy.licence("HC5", allow_adjacent=False, allow_dense=True) is True
    assert policy.licence("HC14", allow_adjacent=True, allow_dense=False) is False
    assert policy.licence("HC14", allow_adjacent=False, allow_dense=True) is True


# ── القاعدةُ تستثني ──────────────────────────────────────────────────


def test_no_rows_means_the_code_exactly(school):
    assert cr.resolve(school, YEAR) == cr.default_policy()


def test_a_row_moves_the_rank(school):
    override(school, "HC5", break_at=cr.NEVER)

    policy = cr.resolve(school, YEAR)

    assert policy.break_at("HC5") == cr.NEVER
    assert policy.overridden == ("HC5",)
    assert policy.break_at("HC6") == cr.DENSE, "ولا يمسّ غيرَه"


def test_a_row_moves_a_soft_weight(school):
    override(school, "thursday_pair", weight=40)

    assert cr.resolve(school, YEAR).weight("thursday_pair") == 40


def test_another_year_is_untouched(school):
    override(school, "HC5", break_at=cr.NEVER)

    assert cr.resolve(school, "2027-2028").break_at("HC5") == cr.RELAXED


def test_a_stale_code_is_ignored_not_fatal(school):
    """قيدٌ حُذف من الشيفرة وبقي صفُّه — يُطرَح ولا يُسقط توليداً."""
    ScheduleConstraintOverride.objects.create(
        school=school, academic_year=YEAR, code="HC99", break_at=cr.NEVER, reason="قديم"
    )

    assert cr.resolve(school, YEAR).overridden == ()


# ── ما لا يُقبل حفظُه ────────────────────────────────────────────────


def test_the_core_refuses_to_be_saved(school):
    from django.core.exceptions import ValidationError

    with pytest.raises(ValidationError) as caught:
        override(school, "HC13", break_at=cr.DENSE)

    assert "النواة" in str(caught.value)


def test_an_unknown_code_is_refused(school):
    from django.core.exceptions import ValidationError

    with pytest.raises(ValidationError):
        override(school, "HC404", break_at=cr.NEVER)


def test_a_hard_constraint_is_not_given_a_weight(school):
    from django.core.exceptions import ValidationError

    with pytest.raises(ValidationError):
        override(school, "HC5", break_at=cr.NEVER, weight=3)


def test_a_soft_constraint_is_not_given_a_rank(school):
    from django.core.exceptions import ValidationError

    with pytest.raises(ValidationError):
        override(school, "gap", break_at=cr.NEVER)


# ── الأثرُ في المولّد ────────────────────────────────────────────────


def _busy_thursday(policy=None):
    """شعبةٌ أخذت حصّةَ الرياضيات يومَ الخميس — والثانيةُ تُطلب."""
    grid = ScheduleGrid(policy=policy)
    grid.place(4, 1, task(grade="G11", level_type="sec"))
    return grid


def test_thursday_holds_by_default_even_in_the_last_round():
    """HC17 رتبتُه `never` — فلا تكسره رخصةٌ مهما ضاق الجدول."""
    grid = _busy_thursday()
    second = task(grade="G11", level_type="sec")

    assert is_slot_valid(grid, 4, 3, second) is False
    assert is_slot_valid(grid, 4, 3, second, allow_adjacent=True, allow_dense=True) is False


def test_a_rank_lets_thursday_bend_in_the_last_round_only(school):
    """وبرتبةٍ من الإدارة يُكسَر — في الملاذ الأخير وحدَه لا قبله."""
    override(school, "HC17", break_at=cr.DENSE)
    grid = _busy_thursday(cr.resolve(school, YEAR))
    second = task(grade="G11", level_type="sec")

    assert is_slot_valid(grid, 4, 3, second) is False, "الجولةُ الأولى تلتزم"
    assert is_slot_valid(grid, 4, 3, second, allow_adjacent=True) is False, "ولا الثانية"
    assert is_slot_valid(grid, 4, 3, second, allow_adjacent=True, allow_dense=True) is True


def test_a_rank_can_tighten_not_only_loosen(school):
    """الرتبةُ تشدّ كما ترخي — وهذا ما لا يقدر عليه زرُّ الإطفاء.

    التلاصقُ يُرخى افتراضاً في الرخصة الأولى؛ فبرتبة `never` لا يُرخى أبداً.
    """
    #: شعبتان ومادّتان لمعلّمٍ واحد — فالمانعُ تلاصقُه هو، لا قسمةُ مادّةٍ
    #: على أيّامها (HC6). واختبارٌ يمرّ لسببٍ غيرِ الذي يدّعيه لا يحرس شيئاً.
    before = task(class_id="c2", subject_id="s2", subject_name="العلوم", subject_code="SCI2")

    grid_default = ScheduleGrid()
    grid_default.place(0, 3, before)
    assert is_slot_valid(grid_default, 0, 4, task(), allow_adjacent=True) is True

    override(school, "HC5", break_at=cr.NEVER)
    grid = ScheduleGrid(policy=cr.resolve(school, YEAR))
    grid.place(0, 3, before)

    assert is_slot_valid(grid, 0, 4, task(), allow_adjacent=True) is False
    assert is_slot_valid(grid, 0, 4, task(), allow_adjacent=True, allow_dense=True) is False


def test_the_relaxed_constraint_still_holds_its_ceiling(school):
    """الرخصةُ ترفع السقفَ من واحدٍ إلى اثنين ولا تُلغي القيد — فلا ثلاثيّة."""
    grid = ScheduleGrid()
    grid.place(0, 2, task(class_id="c2", subject_id="s2", subject_code="SCI2"))
    grid.place(0, 3, task(class_id="c3", subject_id="s3", subject_code="HIS"))

    assert is_slot_valid(grid, 0, 4, task(), allow_adjacent=True) is False


def test_the_policy_is_stored_with_the_generation_snapshot(school):
    override(school, "HC17", break_at=cr.DENSE)

    stored = cr.resolve(school, YEAR).as_dict()

    assert stored["overridden"] == ["HC17"]
    assert stored["breaks"]["HC17"] == cr.DENSE

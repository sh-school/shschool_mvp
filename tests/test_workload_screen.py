"""[WORKLOAD] شاشةُ إسناد الأنصبة — المرحلةُ الأولى قراءةٌ محضة.

وأخطرُ ما قد تفعله هذه الشاشةُ أن تملأ «النصابَ المعتمد» من الحصص المرصودة.
فمعلّمٌ بأربعَ عشرةَ حصّةً قد يكون نصابُه ثمانيَ عشرةَ وله تخفيضُ منسّقِ مادّة،
وحينئذٍ يصير التاريخُ سياسةً بلا قرارٍ من أحد:

    HistoricalAssignment → Proposal        (وليس → Truth)

ويُثبَّت هنا كذلك أنّ البوّابةَ **طبقتان**: ما تملك القاعدةُ اليومَ الإجابةَ
عنه، وما ينتظر كيانَي النصاب والمؤهّلات. وخلطُهما يجعل أربعةَ شروطٍ خضراءَ
فعلاً تبدو ناقصةً لأنّ نظامَ تخطيطٍ لم يُبنَ بعد.
"""

import pytest

from academic_management.workload_service import (
    ENFORCEABLE,
    NEEDS_MODELS,
    UNKNOWN,
    gate,
    plan_context,
    section_view,
    subject_view,
    teacher_view,
    totals,
)
from operations.schedule_profile import Lesson


def lesson(*, teacher="t1", name="أحمد", klass="7/1", code="MATH", day=0, period=1, grade="G7"):
    return Lesson(
        teacher_id=teacher,
        teacher_name=name,
        class_id=klass,
        class_name=klass,
        class_label=klass,
        subject_id=f"id-{code}",
        subject_name=code,
        subject_code=code,
        day=day,
        period=period,
        grade=grade,
        level_type="prep",
    )


def assignment(*, teacher="t1", name="أحمد", klass="7/1", code="MATH", weekly=5, grade="G7"):
    return {
        "teacher_id": teacher,
        "teacher_name": name,
        "class_id": klass,
        "section": klass,
        "grade": grade,
        "subject_id": f"id-{code}",
        "code": code,
        "name": code,
        "weekly_periods": weekly,
    }


# ── الحدُّ المعرفيّ: المعتمَدُ يبقى فارغاً ────────────────────────────


def test_the_approved_load_is_never_filled_from_the_observed_schedule():
    """يُعرض المرصودُ بجانبه، ولا يُنسخ فيه."""
    lessons = [lesson(day=d) for d in range(5)]

    row = teacher_view(lessons, [assignment(weekly=5)])[0]

    assert row["observed_weekly"] == 5
    assert row["approved_weekly"] is None
    assert row["reductions"] is None
    assert row["required_teaching"] is None
    assert row["qualifications"] is None


def test_the_plan_context_names_the_absent_version_instead_of_implying_one():
    """الشاشةُ عن عامٍ ونسخة، لا عن «الحالة الحاليّة» بلا تاريخ."""
    plan = plan_context(None, "2026-2027")

    assert plan["academic_year"] == "2026-2027"
    assert plan["plan_version"] is None
    assert plan["is_read_only"]
    assert "لا توجد" in plan["plan_status"]


# ── منظورُ المعلّم ──────────────────────────────────────────────────


def test_the_teacher_matrix_lists_periods_per_subject_and_section():
    lessons = [lesson(klass="7/1", day=d) for d in range(5)]
    lessons += [lesson(klass="7/2", day=d) for d in range(3)]

    row = teacher_view(lessons, [])[0]

    assert row["cells"] == [
        {"code": "MATH", "section": "7/1", "periods": 5},
        {"code": "MATH", "section": "7/2", "periods": 3},
    ]
    assert row["observed_weekly"] == 8
    assert sum(c["periods"] for c in row["cells"]) == row["observed_weekly"]


def test_a_teacher_present_only_in_the_schedule_shows_a_zero_assignment():
    row = teacher_view([lesson()], [])[0]

    assert row["observed_weekly"] == 1
    assert row["assigned_weekly"] == 0
    assert row["delta"] == 1


# ── منظورُ المادّة: Coverage Matrix ─────────────────────────────────


def test_the_coverage_matrix_totals_demand_against_what_is_assigned():
    """أربعُ شعبٍ × خمسِ حصص = عشرون، فإن أُسنِد تسعةَ عشرَ ظهر الفرق."""
    lessons = [lesson(klass=f"7/{s}", day=d) for s in range(1, 5) for d in range(5)]
    rows = [assignment(klass=f"7/{s}", weekly=5) for s in range(1, 4)]
    rows.append(assignment(klass="7/4", weekly=4))

    group = subject_view(lessons, rows)[0]

    assert group["demand"] == 20
    assert group["covered"] == 19
    assert group["delta"] == 1
    assert [s["section"] for s in group["sections"]] == ["7/1", "7/2", "7/3", "7/4"]


def test_a_section_assigned_without_a_teacher_is_named_unknown_not_blank():
    rows = [assignment(weekly=5)]
    rows[0]["teacher_name"] = UNKNOWN

    group = subject_view([lesson()], rows)[0]

    assert group["unstaffed"] == 1


# ── منظورُ الشعبة ───────────────────────────────────────────────────


def test_the_section_view_lists_every_subject_with_its_teacher():
    lessons = [lesson(code="MATH", day=d) for d in range(4)]
    lessons += [lesson(code="SCI", name="خالد", teacher="t2", day=d) for d in range(2)]

    row = section_view(lessons, [])[0]

    assert row["label"] == "7/1"
    assert row["weekly"] == 6
    assert row["teachers"] == 2
    assert [s["code"] for s in row["subjects"]] == ["MATH", "SCI"]


# ── البوّابة: طبقتان ────────────────────────────────────────────────


def test_the_gate_separates_what_is_checkable_now_from_what_needs_new_models():
    lessons = [lesson(day=d) for d in range(5)]

    result = gate(lessons, [assignment(weekly=5)])

    assert result["enforceable_total"] == 4
    assert result["blocked_total"] == 4
    assert result["enforceable_passed"] == 4, "الواقعُ سليمٌ ولا ينتظر نموذجاً"
    pending = [c for c in result["checks"] if c["layer"] == NEEDS_MODELS]
    assert all(c["passed"] is None for c in pending), "الموقوفُ لا يُقال إنّه فشل"


def test_a_real_inconsistency_turns_an_enforceable_check_red():
    lessons = [lesson(day=d) for d in range(6)]

    result = gate(lessons, [assignment(weekly=5)])

    failed = [c for c in result["checks"] if c["layer"] == ENFORCEABLE and not c["passed"]]
    assert failed, "ستُّ حصصٍ مقابل خمسٍ مُسنَدة"
    assert result["issues"]


@pytest.mark.parametrize("field", ["approved_weekly", "required_teaching"])
def test_no_perspective_ever_emits_a_number_for_the_approved_layer(field):
    lessons = [lesson(day=d) for d in range(5)]

    assert teacher_view(lessons, [assignment(weekly=5)])[0][field] is None


def test_totals_report_both_sides_without_reconciling_them_silently():
    lessons = [lesson(day=d) for d in range(6)]

    data = totals(lessons, [assignment(weekly=5)])

    assert data["lessons"] == 6
    assert data["assigned"] == 5, "لا يُخفى الفارقُ بمتوسّطٍ أو بجمعٍ واحد"


# ── طبقةُ الخطّة فوق الشاشة ─────────────────────────────────────────


@pytest.mark.django_db
def test_the_screen_shows_unknown_when_no_plan_exists(db):
    from academic_management.workload_service import plan_display

    view = plan_display(None, observed=18)

    assert view["state"] == "none"
    assert view["label"] == UNKNOWN
    assert view["approved"] is None


@pytest.mark.django_db
def test_a_draft_plan_is_shown_as_a_draft_and_never_as_a_number(db):
    """ما لم يُوقَّع لا يُقرأ قراراً — ولو كان أحدثَ نسخة."""
    from academic_management.models import DRAFT, TeacherWorkloadPlan
    from academic_management.workload_service import plan_display
    from core.models import CustomUser, School

    school = School.objects.create(name="م", code="S1")
    teacher = CustomUser.objects.create(national_id="30000000001", full_name="أحمد")
    row = TeacherWorkloadPlan.objects.create(
        school=school,
        teacher=teacher,
        academic_year="2026-2027",
        plan_version=1,
        required_weekly_periods=18,
        status=DRAFT,
    )

    view = plan_display(row, observed=18)

    assert view["state"] == "draft"
    assert view["approved"] is None
    assert "مسوّدة" in view["label"]


@pytest.mark.django_db
def test_an_approved_plan_shows_the_number_its_source_and_the_discrepancy(db):
    from academic_management.models import APPROVED, TeacherWorkloadPlan
    from academic_management.workload_service import plan_display
    from core.models import CustomUser, School

    school = School.objects.create(name="م", code="S2")
    teacher = CustomUser.objects.create(national_id="30000000002", full_name="خالد")
    row = TeacherWorkloadPlan.objects.create(
        school=school,
        teacher=teacher,
        academic_year="2026-2027",
        plan_version=2,
        required_weekly_periods=18,
        reduction_periods=2,
        reduction_reason="منسّق مادّة",
        status=APPROVED,
        required_source_kind="manual",
        required_source_reference="تعميم 7",
        reduction_source="school",
        reduction_source_reference="محضر 12",
    )

    view = plan_display(row, observed=18)

    assert view["state"] == "approved"
    assert (view["required"], view["reductions"], view["approved"]) == (18, 2, 16)
    assert view["delta"] == 2, "المرصود 18 والمعتمد 16"
    assert view["is_error"] is False, "الفرقُ يحتاج تفسيراً ولا يُسمّى خطأً"
    assert view["version"] == 2
    # مصدرُ النصاب ومصدرُ التخفيض قرارانِ مختلفان — فلا يُعرضان في سطرٍ واحد.
    assert view["required_source_reference"] == "تعميم 7"
    assert view["reduction_source_reference"] == "محضر 12"


@pytest.mark.django_db
def test_the_approved_plan_check_stays_pending_while_no_plan_is_approved(db):
    from academic_management.workload_service import NEEDS_MODELS, gate

    lessons = [lesson(day=d) for d in range(5)]

    checks = gate(lessons, [assignment(weekly=5)], plans={})["checks"]
    pending = [c for c in checks if c["layer"] == NEEDS_MODELS]

    assert all(c["passed"] is None for c in pending)

"""[SCHEDULER] النصابُ المرصود — يُثبَّت حسابُه قبل أن يُبنى عليه إسناد.

    ObservedScheduledWorkload ≠ ApprovedWorkload

وهذا ما يحرسه هذا الملفّ. فأخطرُ ما قد يفعله المقياسُ أن يُخرج «فلانٌ ناقصُ
أربعِ حصص» عن معلّمٍ له تخفيضُ منسّقِ مادّةٍ معتمَد. والجدولُ لا يحمل هذه
الحقيقة أصلاً — فالمقارنةُ هنا بين الجدول و`SubjectClassAssignment` وحدهما،
وكلاهما ليس النصابَ المعتمَد.

ويُثبَّت هنا أيضاً أنّ المطابقة **على مستوى الخليّة** لا المجموع: معلّمان
تبادلا شعبتين يظهر مجموعُ كلٍّ منهما سليماً وهما مخطئان في الاثنتين.
"""

import pytest

from operations.schedule_profile import Lesson
from operations.workload_profile import (
    ASSIGNMENT_ONLY,
    DIFFERENT_COUNT,
    DIFFERENT_TEACHER,
    MATCH,
    SCHEDULE_ONLY,
    demand_coverage,
    observed_workload,
    reconcile_cells,
    reconcile_teachers,
)


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
        level_type="prep" if grade in ("G7", "G8", "G9") else "sec",
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


# ── النصابُ المرصود ──────────────────────────────────────────────────


def test_the_observed_load_is_broken_down_by_subject_and_section():
    lessons = [lesson(klass="7/1", day=d) for d in range(3)]
    lessons += [lesson(klass="7/2", day=d) for d in range(2)]
    lessons += [lesson(klass="10/1", code="SCI", grade="G10")]

    row = observed_workload(lessons)["t1"]

    assert row.observed_weekly == 6
    assert row.per_subject_class == {"MATH·7/1": 3, "MATH·7/2": 2, "SCI·10/1": 1}
    assert row.sections_per_subject == {"MATH": 2, "SCI": 1}
    assert row.multi_subject, "مادّتان"
    assert row.multi_level, "إعداديٌّ وثانويّ — والمرحلةُ لا تُشتقّ من الصفّ"
    assert sorted(row.grades) == ["G10", "G7"]


def test_a_single_subject_single_level_teacher_is_flagged_as_neither():
    row = observed_workload([lesson(day=d) for d in range(4)])["t1"]

    assert not row.multi_subject
    assert not row.multi_level


def test_a_split_period_counts_a_full_lesson_for_each_teacher_in_it():
    """خانةٌ واحدةٌ تحمل مادّتين لمجموعتين — وكلا المعلّمين يعمل حصّةً كاملة.

    فلا يُنقَص نصابُ أحدهما لأنّ زميلَه يشاركه التوقيت.
    """
    lessons = [
        lesson(teacher="t1", klass="11/1", code="CS", period=3),
        lesson(teacher="t2", name="خالد", klass="11/1", code="BUS", period=3),
    ]

    rows = observed_workload(lessons)

    assert rows["t1"].observed_weekly == rows["t2"].observed_weekly == 1
    assert rows["t1"].split_periods == rows["t2"].split_periods == 1


# ── المطابقة على مستوى الخليّة ───────────────────────────────────────


def test_two_teachers_who_swapped_sections_are_caught_although_their_totals_match():
    """المجموعُ يخدع: كلاهما خمسُ حصصٍ جدولاً وخمسٌ إسناداً — والشعبتان مقلوبتان."""
    lessons = [lesson(teacher="t1", name="أحمد", klass="7/1")]
    lessons += [lesson(teacher="t2", name="خالد", klass="7/2")]
    rows = [
        assignment(teacher="t1", name="أحمد", klass="7/2", weekly=1),
        assignment(teacher="t2", name="خالد", klass="7/1", weekly=1),
    ]

    by_teacher = reconcile_teachers(observed_workload(lessons), rows)
    cells = {c["section"]: c for c in reconcile_cells(lessons, rows)}

    assert all(t["status"] == MATCH for t in by_teacher.values()), "المجاميعُ سليمة"
    assert cells["7/1"]["status"] == DIFFERENT_TEACHER
    assert cells["7/2"]["status"] == DIFFERENT_TEACHER


def test_a_cell_scheduled_more_than_it_was_assigned_reports_the_signed_difference():
    lessons = [lesson(day=d) for d in range(6)]

    cell = reconcile_cells(lessons, [assignment(weekly=5)])[0]

    assert cell["status"] == DIFFERENT_COUNT
    assert (cell["scheduled"], cell["assigned"], cell["delta"]) == (6, 5, 1)


def test_a_cell_present_on_only_one_side_is_named_by_the_side_it_is_missing_from():
    lessons = [lesson(klass="7/1")]
    rows = [assignment(klass="7/2", weekly=4)]

    cells = {c["section"]: c for c in reconcile_cells(lessons, rows)}

    assert cells["7/1"]["status"] == SCHEDULE_ONLY
    assert cells["7/2"]["status"] == ASSIGNMENT_ONLY
    assert cells["7/2"]["delta"] == -4


# ── ميزانيّةُ الصفّ × المادّة ────────────────────────────────────────


def test_the_grade_budget_reports_an_unassigned_period():
    """أربعُ شعبٍ × خمسِ حصص = عشرون. فإن أُسنِد تسعةَ عشرَ فحصّةٌ بلا معلّم."""
    lessons = [lesson(klass=f"7/{s}", day=d) for s in range(1, 5) for d in range(5)]
    rows = [assignment(klass=f"7/{s}", weekly=5) for s in range(1, 4)]
    rows.append(assignment(klass="7/4", weekly=4))

    row = demand_coverage(lessons, rows)[0]

    assert (row["sections"], row["scheduled"], row["assigned"]) == (4, 20, 19)
    assert row["delta"] == 1


def test_an_assignment_without_a_teacher_is_counted_as_unstaffed():
    lessons = [lesson()]
    rows = [assignment(weekly=1)]
    rows[0]["teacher_id"] = ""

    assert demand_coverage(lessons, rows)[0]["unstaffed"] == 1


# ── الحدُّ المعرفيّ ──────────────────────────────────────────────────


def test_nothing_in_this_module_claims_to_know_the_approved_load():
    """لا حقلَ اسمُه `required` ولا `approved` — لأنّه ليس في الجدول.

    ولو ظهر واحدٌ منهما لصار الرقمُ المرصودُ يُقرأ حكماً إداريّاً، وهو ما
    يجعل معلّماً بثماني حصصٍ «ناقصاً» وقد يكون تخفيضُه معتمَداً.
    """
    lessons = [lesson()]
    rows = [assignment(weekly=1)]

    keys = set(reconcile_cells(lessons, rows)[0]) | set(
        next(iter(reconcile_teachers(observed_workload(lessons), rows).values()))
    )

    assert not {k for k in keys if "required" in k or "approved" in k}
    assert "scheduled" in keys and "assigned" in keys


@pytest.mark.parametrize("field", ["required_weekly_periods", "reduction_periods", "approved_by"])
def test_the_workload_record_does_not_exist_yet(field):
    """`TeacherWorkloadPlan` قرارٌ إداريٌّ لم يُبنَ — ولا يُصطنَع من الجدول."""
    from operations import models

    assert not hasattr(
        models, "TeacherWorkloadPlan"
    ), f"إن بُني الكيانُ فحقلُ {field} يصير مصدرَ النصاب، ويُعاد النظر في هذه الوحدة"

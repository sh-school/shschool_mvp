"""[SCHEDULE-V2] محوِّلُ المهامّ إلى مدخلات CP-SAT (W-20261003-015، V2-S2).

المحوِّلُ طبقةُ مدخلاتٍ صِرفةٌ: يقرأ ما بناه `build_tasks` وما حمّله `load_inputs`، لا JSON ولا حلّال. فتقارن هذه الاختباراتُ
المدخلاتِ بالحقيقة الحيّة (حصصٌ، أعضاءٌ، حجبٌ، جرسٌ) — وبمهامّ مبنيّةٍ باليد حيث تلزم الحالاتُ الحدّيّة (منقسمة، مورد).
"""

from datetime import time

import pytest

from operations import cpsat_adapter
from operations.cpsat_adapter import build_inputs
from operations.models import Subject, SubjectClassAssignment, TeacherExemption, TimeSlotConfig
from operations.scheduler import Member, Task, bell_lookup, build_tasks, load_inputs
from tests.conftest import ClassGroupFactory, MembershipFactory, RoleFactory, UserFactory

YEAR = "2026-2027"


def _task(**overrides):
    base = {
        "class_id": "C1",
        "class_name": "7/1",
        "subject_id": "S1",
        "subject_name": "رياضيات",
        "subject_code": "MATH",
        "teacher_id": "T1",
        "teacher_name": "معلّم",
        "weekly_periods": 3,
        "level_type": "prep",
    }
    base.update(overrides)
    return Task(**base)


def _lookup(day, period, band=""):
    """جرسٌ اصطناعيّ: الحصصُ 1-3 متلاصقة، وفسحةٌ بعد الثالثة، ثمّ 4-7 متلاصقة."""
    starts = {1: 430, 2: 480, 3: 530, 4: 600, 5: 650, 6: 700, 7: 750}
    start = starts[period]
    return time(start // 60, start % 60), time((start + 50) // 60, (start + 50) % 60)


# ── الحصص والأعضاء ─────────────────────────────────────────────────────


def test_the_demand_sums_the_task_spans_per_class_subject_teacher():
    tasks = [
        _task(span=2),
        _task(span=1),
        _task(subject_id="S2", subject_name="علوم", weekly_periods=2),
    ]

    inputs = build_inputs(tasks)

    rows = {(r.cls, r.subj, r.teacher): r.n for r in inputs.demand}
    assert rows == {("C1", "S1", "T1"): 3, ("C1", "S2", "T1"): 1}
    assert inputs.total == 4


def test_a_double_period_marks_its_subject_as_double():
    inputs = build_inputs([_task(span=2), _task(subject_id="S2", subject_name="علوم")])

    assert inputs.doubles == {"S1"}


def test_a_split_task_gives_one_row_per_member_joined_by_the_same_key():
    members = [Member("T1", "أ", "S1", "رياضيات", "MATH"), Member("T2", "ب", "S2", "فيزياء", "PHY")]

    inputs = build_inputs([_task(members=members, span=1)])

    assert sorted(r.teacher for r in inputs.demand) == ["T1", "T2"]
    assert len({r.joint for r in inputs.demand}) == 1 and inputs.demand[0].joint != ""
    assert inputs.total == 2, "كلُّ عضوٍ يُحتسب حصّتَه — مجموعُ الأعضاء لا المهامّ"


def test_a_plain_task_has_no_joint_and_a_parallel_group_is_kept_as_elec():
    inputs = build_inputs([_task(parallel_group="G-1")])

    assert inputs.demand[0].joint == "" and inputs.demand[0].elec == "G-1"


def test_resources_carry_capacity_and_the_subjects_that_use_them():
    tasks = [
        _task(resources=(("R1", 2, False),)),
        _task(subject_id="S2", subject_name="علوم", resources=(("R1", 2, False),)),
    ]

    inputs = build_inputs(tasks)

    assert inputs.res_cap == {"R1": 2}
    assert inputs.res_subjects == {"R1": frozenset({"S1", "S2"})}


# ── الحجب ──────────────────────────────────────────────────────────────


def test_a_fully_blocked_day_is_ex_full_and_a_partial_one_is_per_period():
    blocked = {("T1", 2, p) for p in range(1, 8)} | {("T1", 4, 3), ("T1", 4, 5)}

    inputs = build_inputs([_task()], blocked_slots=blocked)

    assert inputs.ex_full == {("T1", 2)}
    assert inputs.ex_period == {("T1", 4, 3), ("T1", 4, 5)}


# ── الجرس والتلاصق ────────────────────────────────────────────────────


def test_touching_periods_come_from_the_clock_not_the_numbers():
    inputs = build_inputs([_task()], bell_lookup=_lookup)

    bell = inputs.bell["|regular"]
    assert bell["periods"] == [1, 2, 3, 4, 5, 6, 7]
    # 3→4 يفصلهما فسحةٌ (580 ثمّ 600) فلا تلاصق؛ والباقي متتابعٌ بلا فاصلٍ (50 دقيقة لكلّ حصّة).
    assert (3, 4) not in bell["touch"] and (1, 2) in bell["touch"] and (4, 5) in bell["touch"]
    assert inputs.times["|regular"][1] == (430, 480)


def test_thursday_period_cap_follows_the_level_not_a_copy_of_the_number():
    prep = build_inputs([_task(level_type="prep")], bell_lookup=_lookup)
    sec = build_inputs([_task(level_type="sec")], bell_lookup=_lookup)

    assert len(prep.periods("C1", 4)) == 6 and len(sec.periods("C1", 4)) == 7
    assert len(prep.periods("C1", 0)) == 7, "غيرُ الخميس سبعٌ دائماً"


def test_inputs_have_no_json_or_solver_dependency():
    source = cpsat_adapter.__file__
    text = open(source, encoding="utf-8").read()

    assert "import json" not in text and "import ortools" not in text and "from ortools" not in text


# ── من `build_tasks` الحيّ: الحقيقةُ نفسُها ────────────────────────────


@pytest.fixture
def live_school(school):
    for period in range(1, 8):
        for day_type in ("regular", "thursday"):
            TimeSlotConfig.objects.create(
                school=school,
                period_number=period,
                start_time=time(6 + period, 0),
                end_time=time(6 + period, 45),
                day_type=day_type,
            )
    role = RoleFactory(school=school, name="teacher")
    group = ClassGroupFactory(school=school, grade="G7", level_type="prep", academic_year=YEAR)
    teachers = []
    for index, weekly in enumerate((5, 3, 4)):
        teacher = UserFactory(full_name=f"معلّم {index}")
        MembershipFactory(user=teacher, school=school, role=role)
        subject = Subject.objects.create(school=school, name_ar=f"مادّة {index}", code=f"S{index}")
        SubjectClassAssignment.objects.create(
            school=school,
            academic_year=YEAR,
            teacher=teacher,
            class_group=group,
            subject=subject,
            weekly_periods=weekly,
            is_active=True,
        )
        teachers.append(teacher)
    TeacherExemption.objects.create(
        school=school,
        teacher=teachers[0],
        academic_year=YEAR,
        exemption_type="full_day",
        day_of_week=2,
        reason="تجربة",
        is_active=True,
    )
    TeacherExemption.objects.create(
        school=school,
        teacher=teachers[1],
        academic_year=YEAR,
        exemption_type="specific_period",
        day_of_week=1,
        period_number=3,
        reason="تجربة",
        is_active=True,
    )
    return school, group, teachers


@pytest.mark.django_db
def test_inputs_from_the_live_build_match_the_assignments_and_exemptions(live_school):
    school, group, teachers = live_school
    tasks = build_tasks(school, YEAR)
    prefs_qs, _prefs, blocked = load_inputs(school, YEAR)

    inputs = build_inputs(tasks, blocked, prefs_qs, bell_lookup(school))

    assert inputs.total == 12 == sum(a.weekly_periods for a in SubjectClassAssignment.objects.all())
    assert {(r.cls, r.teacher): r.n for r in inputs.demand} == {
        (str(group.id), str(teachers[0].id)): 5,
        (str(group.id), str(teachers[1].id)): 3,
        (str(group.id), str(teachers[2].id)): 4,
    }
    assert inputs.ex_full == {(str(teachers[0].id), 2)}
    assert inputs.ex_period == {(str(teachers[1].id), 1, 3)}
    assert len(inputs.periods(str(group.id), 4)) == 6, "إعداديّ ⇒ ستُّ حصصٍ في الخميس"
    assert inputs.class_names[str(group.id)] == str(group)

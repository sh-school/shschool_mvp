"""[SCHEDULE] المُقيِّمُ المستقلّ للجدول (V2-S1، ADR-0008 §3 و§5).

يقرأ أيَّ جدول — حيّاً أو مسودّةً أو ناتجَ حلّالٍ خارجيٍّ بالمعرّفات — ويُخرج InfeasibilityValue ومخالفاتِ كلّ
قيدٍ صلبٍ (بحكم المدقّق الرسميّ نفسِه) وObjectiveValue للمرنة وحدَها، بلا أسماءَ وبلا كتابةٍ في القاعدة.
"""

import json
from collections import Counter
from datetime import time
from io import StringIO

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from operations.models import ScheduleSlot, Subject, SubjectClassAssignment, TimeSlotConfig
from operations.schedule_evaluator import (
    EvaluatorInputError,
    evaluate_slots,
    generation_slots,
    relaxations_from_payload,
    slots_from_payload,
)
from operations.scheduler import generate_schedule
from operations.scheduler_audit import grid_breaches
from operations.scheduler_live import load_grid
from tests.conftest import ClassGroupFactory, MembershipFactory, RoleFactory, UserFactory

pytestmark = pytest.mark.django_db

YEAR = "2026-2027"
NAMES = ("معلّم أوّل", "معلّم ثانٍ")


@pytest.fixture
def scene(school):
    """شعبةٌ واحدة، مادّتان بثلاث حصصٍ لكلٍّ منهما، معلّمان — جدولٌ صغيرٌ يولَّد في ثوانٍ."""
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
    for index, name in enumerate(NAMES):
        teacher = UserFactory(full_name=name)
        MembershipFactory(user=teacher, school=school, role=role)
        subject = Subject.objects.create(school=school, name_ar=f"مادّة {index}", code=f"EV{index}")
        SubjectClassAssignment.objects.create(
            school=school,
            academic_year=YEAR,
            teacher=teacher,
            class_group=group,
            subject=subject,
            weekly_periods=3,
            is_active=True,
        )
    return school


@pytest.fixture
def generated(scene):
    result = generate_schedule(scene, YEAR)
    return scene, result["generation"]


def _payload(slots, status="OPTIMAL"):
    rows = [
        [
            str(s.class_group_id),
            str(s.subject_id),
            str(s.teacher_id),
            s.day_of_week,
            s.period_number,
        ]
        for s in slots
    ]
    return {"solver": {"status": status, "seed": 7, "workers": 4, "seconds": 1.5}, "slots": rows}


# ── الحكم ──────────────────────────────────────────────────────────────


def test_a_complete_clean_draft_is_accepted_with_all_three_numbers(generated):
    school, generation = generated

    result = evaluate_slots(school, YEAR, generation_slots(generation))

    assert result.infeasibility_value == 0 and result.required_periods == 6
    assert result.hard_total == 0 and result.accepted
    assert isinstance(result.objective_value, float)


def test_the_hard_counts_are_the_official_auditors_counts_exactly(generated):
    """موضعُ كلّ حصّةٍ على الأحد: يخالف التوزيع — والمُقيِّم يطابق grid_breaches رمزاً برمز."""
    school, generation = generated
    rows = list(generation_slots(generation).order_by("subject_id", "day_of_week", "period_number"))
    first_subject = rows[0].subject_id
    for period, row in enumerate([r for r in rows if r.subject_id == first_subject], start=1):
        row.day_of_week, row.period_number = 0, period

    result = evaluate_slots(school, YEAR, rows)

    loaded = load_grid(school, YEAR, rows)
    official = Counter(
        b.code for b in grid_breaches(loaded["grid"], loaded["tasks"], loaded["blocked"])
    )
    assert result.hard_breaches == dict(official)
    assert result.hard_total > 0 and not result.accepted


def test_a_missing_lesson_is_reported_as_infeasibility_by_ids(generated):
    school, generation = generated
    rows = list(generation_slots(generation))
    dropped = rows.pop()

    result = evaluate_slots(school, YEAR, rows)

    assert result.infeasibility_value == 1 and result.required_periods == 6
    assert result.unplaced == (
        (str(dropped.class_group_id)[:8], str(dropped.subject_id)[:8], str(dropped.teacher_id)[:8]),
    )
    assert not result.accepted and any("InfeasibilityValue" in note for note in result.notes)


def test_an_empty_schedule_reports_the_whole_demand_as_unplaced(scene):
    result = evaluate_slots(scene, YEAR, [])

    assert result.infeasibility_value == 6 and result.placed_periods == 0
    assert len(result.unplaced) == 6 and len(set(result.unplaced)) == 2 and not result.accepted


# ── المصدر الخارجيّ ─────────────────────────────────────────────────────


def test_an_external_payload_scores_exactly_like_the_database_rows(generated):
    school, generation = generated
    rows = list(generation_slots(generation))
    slots, solver = slots_from_payload(_payload(rows))

    from_db = evaluate_slots(school, YEAR, rows)
    from_json = evaluate_slots(school, YEAR, slots, solver)

    assert from_json.fingerprint == from_db.fingerprint
    assert from_json.hard_breaches == from_db.hard_breaches
    assert from_json.objective_value == from_db.objective_value
    assert from_json.infeasibility_value == from_db.infeasibility_value


@pytest.mark.parametrize(
    ("status", "verdict_part"),
    [
        ("OPTIMAL", "أمثل"),
        ("FEASIBLE", "غيرُ مُثبَتِ الأمثليّة"),
        ("INFEASIBLE", "بالبرهان"),
        ("UNKNOWN", "ضيقُ وقت"),
    ],
)
def test_the_solver_status_is_told_as_text_and_never_inflated(generated, status, verdict_part):
    school, generation = generated
    rows = list(generation_slots(generation))
    slots, solver = slots_from_payload(_payload(rows, status))

    result = evaluate_slots(school, YEAR, slots, solver)

    assert verdict_part in result.verdict
    assert result.solver["seed"] == 7 and result.solver["workers"] == 4


@pytest.mark.parametrize(
    "payload",
    [
        {"slots": [], "extra": 1},
        {"slots": [["c", "s", "t", 0, 1, "اسم"]]},
        {"slots": [["c", "s", "t", 9, 1]]},
        {"slots": [["c", "s", "t", 0, 0]]},
        {"slots": [["c", "s", "", 0, 1]]},
        {"slots": [], "solver": {"status": "OPTIMAL", "seed": 1}},
        {"slots": [], "solver": {"status": "GOOD", "seed": 1, "workers": 1}},
        {"slots": [], "solver": {"status": "OPTIMAL", "seed": 1, "workers": 1, "teacher": "x"}},
        {"slots": "not a list"},
        [],
    ],
)
def test_an_undeclared_field_or_a_bad_value_is_refused(payload):
    with pytest.raises(EvaluatorInputError):
        slots_from_payload(payload)


# ── لا أسماء، ولا كتابة ──────────────────────────────────────────────────


def test_the_command_prints_no_name_and_writes_nothing(generated, tmp_path):
    school, generation = generated
    path = tmp_path / "solver.json"
    path.write_text(
        json.dumps(_payload(list(generation_slots(generation)), "FEASIBLE")), encoding="utf-8"
    )
    before = (ScheduleSlot.objects.count(), SubjectClassAssignment.objects.count())
    out = StringIO()

    call_command(
        "evaluate_schedule", slots_json=str(path), school=school.code, year=YEAR, stdout=out
    )

    text = out.getvalue()
    assert "InfeasibilityValue = 0" in text and "ObjectiveValue" in text and "مقبول" in text
    assert "غيرُ مُثبَتِ الأمثليّة" in text
    for name in NAMES:
        assert name not in text
    assert (ScheduleSlot.objects.count(), SubjectClassAssignment.objects.count()) == before


def test_the_command_exits_non_zero_when_the_schedule_is_not_accepted(scene, tmp_path):
    path = tmp_path / "empty.json"
    path.write_text(json.dumps({"slots": []}), encoding="utf-8")

    with pytest.raises(SystemExit) as stop:
        call_command(
            "evaluate_schedule",
            slots_json=str(path),
            school=scene.code,
            year=YEAR,
            stdout=StringIO(),
        )

    assert stop.value.code == 1


def test_the_command_refuses_a_malformed_file_by_name(scene, tmp_path):
    path = tmp_path / "bad.json"
    path.write_text(json.dumps({"slots": [], "teacher_name": "x"}), encoding="utf-8")

    with pytest.raises(CommandError):
        call_command(
            "evaluate_schedule",
            slots_json=str(path),
            school=scene.code,
            year=YEAR,
            stdout=StringIO(),
        )


def test_the_fingerprint_is_stable_for_the_same_schedule(generated):
    school, generation = generated
    rows = list(generation_slots(generation))

    assert (
        evaluate_slots(school, YEAR, rows).fingerprint
        == evaluate_slots(school, YEAR, list(reversed(rows))).fingerprint
    )


# ── تخفيف HC5 المعلَن: حصّتان متتاليتان لا ثلاث (قرار المالك 2026-10-09) ──────────────


@pytest.fixture
def run_scene(school):
    """ثلاثُ شعبٍ ومعلّمٌ واحدٌ يدرّس كلاً منها حصّةً، وحصصُ اليوم متلاصقةٌ (فراغ عشر دقائق)."""
    from types import SimpleNamespace

    for period in range(1, 8):
        for day_type in ("regular", "thursday"):
            TimeSlotConfig.objects.create(
                school=school,
                period_number=period,
                start_time=time(6 + period, 0),
                end_time=time(6 + period, 50),
                day_type=day_type,
            )
    teacher = UserFactory(full_name="معلّم التتابع")
    other = UserFactory(full_name="معلّم آخر")
    subject = Subject.objects.create(school=school, name_ar="مادّة التتابع", code="RUN")
    groups = [
        ClassGroupFactory(school=school, grade="G7", level_type="prep", academic_year=YEAR)
        for _ in range(3)
    ]
    for group in groups:
        SubjectClassAssignment.objects.create(
            school=school,
            academic_year=YEAR,
            teacher=teacher,
            class_group=group,
            subject=subject,
            weekly_periods=1,
            is_active=True,
        )

    def slots(*cells):
        return [
            SimpleNamespace(
                class_group_id=str(groups[g].pk),
                subject_id=str(subject.pk),
                teacher_id=str(teacher.pk),
                day_of_week=day,
                period_number=period,
            )
            for g, day, period in cells
        ]

    return SimpleNamespace(school=school, teacher=str(teacher.pk), other=str(other.pk), slots=slots)


def test_without_a_declared_relaxation_two_touching_lessons_stay_a_hard_breach(run_scene):
    result = evaluate_slots(
        run_scene.school, YEAR, run_scene.slots((0, 0, 1), (1, 0, 2), (2, 1, 1))
    )

    assert result.hard_breaches.get("HC5") == 1 and result.eased == {}


def test_a_declared_run_cap_2_turns_a_pair_into_a_note_not_a_breach(run_scene):
    slots = run_scene.slots((0, 0, 1), (1, 0, 2), (2, 1, 1))

    result = evaluate_slots(run_scene.school, YEAR, slots, None, {run_scene.teacher: 2})

    assert "HC5" not in result.hard_breaches and result.eased == {"HC5": 1}
    assert any("HC5" in note and "حصّتان متتاليتان" in note for note in result.notes)


def test_a_run_of_three_stays_a_hard_breach_even_with_the_relaxation(run_scene):
    slots = run_scene.slots((0, 0, 1), (1, 0, 2), (2, 0, 3))

    result = evaluate_slots(run_scene.school, YEAR, slots, None, {run_scene.teacher: 2})

    assert result.hard_breaches.get("HC5", 0) >= 1


def test_a_relaxation_for_another_teacher_eases_nothing(run_scene):
    slots = run_scene.slots((0, 0, 1), (1, 0, 2), (2, 1, 1))

    result = evaluate_slots(run_scene.school, YEAR, slots, None, {run_scene.other: 2})

    assert result.hard_breaches.get("HC5") == 1 and result.eased == {}


def test_the_relaxation_restores_the_task_caps_so_the_next_call_is_strict(run_scene):
    slots = run_scene.slots((0, 0, 1), (1, 0, 2), (2, 1, 1))
    evaluate_slots(run_scene.school, YEAR, slots, None, {run_scene.teacher: 2})

    again = evaluate_slots(run_scene.school, YEAR, slots)

    assert again.hard_breaches.get("HC5") == 1


def test_relaxations_are_read_from_the_payload_and_anything_else_is_refused():
    row = {"teacher": "T1", "code": "HC5", "original": "no_touch", "relaxed": "run_cap_2"}
    assert relaxations_from_payload({"slots": [], "relaxations": [row]}) == {"T1": 2}
    assert relaxations_from_payload({"slots": []}) == {}
    slots_from_payload({"slots": [], "relaxations": [row]})  # المفتاحُ معلَنٌ فلا يُرفض
    for bad in (
        [{**row, "code": "HC22"}],
        [{**row, "relaxed": "run_cap_3"}],
        [{**row, "original": "other"}],
        [{**row, "extra": 1}],
        [{"teacher": "T1"}],
        [{**row, "teacher": ""}],
        "not a list",
    ):
        with pytest.raises(EvaluatorInputError):
            relaxations_from_payload({"slots": [], "relaxations": bad})

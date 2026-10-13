"""[SCHEDULE] مشغِّلُ توليد V2 وبوّابتُه (V2-S4/S5، ADR-0008 §3).

النموذجُ (v2-core) والهدفُ (v2-objective) يُحقنان مزيّفَين عبر العقد (`ModelBuilder`/`Solver`)، فيُختبر المشغِّلُ نفسُه:
مصيرُ كلّ حالةِ حلّال، ورفضُ المُقيِّم المستقلّ، والمسودّةُ غيرُ المنشورة، والاعتمادُ بالقدرة والبصمة، وإعادةُ الإنتاج.
"""

import json
from datetime import time
from io import StringIO
from pathlib import Path
from types import SimpleNamespace

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from core.models import AuditLog
from operations.cpsat_adapter import CpSatInputs, DemandRow
from operations.models import (
    ScheduleGeneration,
    ScheduleSlot,
    Subject,
    SubjectClassAssignment,
    TimeSlotConfig,
)
from operations.scheduler import generate_schedule
from operations.scheduler_v2 import runner
from tests.conftest import ClassGroupFactory, MembershipFactory, RoleFactory, UserFactory

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _no_real_objective(monkeypatch):
    """بوجود النواة والهدف (ortools) يصير الهدفُ الافتراضيّ حقيقياً ويقرأ `built.x` الذي لا يملكه المزيَّف؛ فيُطفأ هنا.

    الاختبارُ الذي يريد الهدفَ يمرّره صراحةً (`objective=`).
    """
    monkeypatch.setattr(runner, "default_objective", lambda: None)


YEAR = "2026-2027"
CONFIG = runner.SolverConfig(seed=11, workers=2, max_seconds=5)
FIXTURE = (
    Path(__file__).resolve().parent.parent / "docs" / "schedule_v2" / "fixture_anonymized.json"
)


@pytest.fixture
def scene(school):
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
    for index in range(2):
        teacher = UserFactory(full_name=f"معلّم {index}")
        MembershipFactory(user=teacher, school=school, role=role)
        subject = Subject.objects.create(school=school, name_ar=f"مادّة {index}", code=f"RN{index}")
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
def known_good(scene):
    """خاناتٌ سليمةٌ بالمعرّفات (من المحرّك الحاليّ) نتّخذها ناتجَ حلّالٍ مزيَّف."""
    generation = generate_schedule(scene, YEAR)["generation"]
    rows = [
        (
            str(s.class_group_id),
            str(s.subject_id),
            str(s.teacher_id),
            s.day_of_week,
            s.period_number,
        )
        for s in ScheduleSlot.objects.filter(generation=generation)
    ]
    ScheduleSlot.objects.filter(generation=generation).delete()
    generation.delete()
    return scene, rows


def _fake(status="OPTIMAL", rows=()):
    """(builder, solver) مزيَّفان: المشغِّلُ لا يعرف أنّ النموذج وهميّ."""
    built = SimpleNamespace(model=object())
    calls = {"builder": 0, "solver": 0}

    def builder(inputs, options=None):
        calls["builder"] += 1
        return built

    def solver(model, config):
        calls["solver"] += 1
        return runner.SolveReport(
            status=status,
            verdict=runner.VERDICTS[status],
            seed=config.seed,
            workers=config.workers,
            seconds=0.1,
            slots=list(rows) if status in ("OPTIMAL", "FEASIBLE") else [],
        )

    return builder, solver, calls


def _generation(school, status="running"):
    return ScheduleGeneration.objects.create(school=school, academic_year=YEAR, status=status)


# ── الحلّال: التمييزُ بين الحالات ─────────────────────────────────────────


def test_optimal_clean_output_becomes_an_inactive_draft_with_bell_times(known_good):
    school, rows = known_good
    builder, solver, _ = _fake("OPTIMAL", rows)
    generation = _generation(school)

    result = runner.run_generation(generation, CONFIG, builder=builder, solver=solver)

    generation.refresh_from_db()
    assert result.ok and generation.status == "draft"
    slots = ScheduleSlot.objects.filter(generation=generation)
    assert slots.count() == len(rows) == generation.total_slots_created
    assert not slots.filter(is_active=True).exists(), "مسودّةٌ لا منشورة"
    first = slots.order_by("day_of_week", "period_number").first()
    assert first.start_time == time(6 + first.period_number, 0), "أوقاتُ TimeSlotConfig"
    snap = generation.config_snapshot
    assert snap["engine"] == "cpsat_v2" and snap["evaluation"]["accepted"] is True
    assert snap["solver"]["status"] == "OPTIMAL" and snap["solver"]["seed"] == 11
    assert runner.is_displayable(generation)


def test_infeasible_is_a_proof_and_unknown_is_a_timeout_and_neither_writes_slots(known_good):
    school, _ = known_good
    for status, reason, wording in (
        ("INFEASIBLE", "infeasible", "INFEASIBLE"),
        ("UNKNOWN", "timeout", "UNKNOWN"),
    ):
        builder, solver, _ = _fake(status)
        generation = _generation(school)
        result = runner.run_generation(generation, CONFIG, builder=builder, solver=solver)
        generation.refresh_from_db()
        assert not result.ok and result.reason == reason
        assert generation.status == "failed" and wording in generation.error_message
        assert generation.config_snapshot["solver"]["status"] == status
        assert not ScheduleSlot.objects.filter(generation=generation).exists()
    assert "ضيقُ وقتٍ لا استحالة" in generation.error_message


def test_feasible_without_proof_is_labelled_not_optimal(known_good):
    school, rows = known_good
    builder, solver, _ = _fake("FEASIBLE", rows)
    generation = _generation(school)
    runner.run_generation(generation, CONFIG, builder=builder, solver=solver)
    generation.refresh_from_db()
    assert generation.config_snapshot["verdict"] == "حلٌّ غيرُ مُثبَتِ الأمثليّة"


# ── البوّابة: المُقيِّمُ المستقلّ يرفض ───────────────────────────────────────


def test_independent_evaluator_rejects_a_double_booked_teacher_and_no_slot_is_written(known_good):
    school, rows = known_good
    first = rows[0]
    other = next(r for r in rows if r[2] != first[2])
    # معلّمٌ في شعبتين… هنا: المعلّمُ الثاني يُسنَد إلى خانة الأوّل نفسِها فيتصادمان.
    bad = [r for r in rows if r != other] + [(other[0], other[1], first[2], first[3], first[4])]
    builder, solver, _ = _fake("OPTIMAL", bad)
    generation = _generation(school)

    result = runner.run_generation(generation, CONFIG, builder=builder, solver=solver)

    generation.refresh_from_db()
    assert not result.ok and result.reason == "rejected"
    assert generation.status == "failed" and "رفض المُقيِّمُ" in generation.error_message
    assert not ScheduleSlot.objects.filter(generation=generation).exists()
    assert not runner.is_displayable(generation)


def test_missing_model_contract_fails_with_a_clear_reason(scene, monkeypatch):
    monkeypatch.setattr(runner, "_load_attr", lambda module, name: None)
    generation = _generation(scene)
    result = runner.run_generation(generation, CONFIG)
    generation.refresh_from_db()
    assert result.reason == "no_model" and generation.status == "failed"


# ── Idempotent + إعادة الإنتاج ──────────────────────────────────────────────


def test_rerun_replaces_the_draft_and_same_inputs_give_same_fingerprint(known_good):
    school, rows = known_good
    builder, solver, _ = _fake("OPTIMAL", rows)
    prints = []
    for _ in range(2):
        generation = _generation(school)
        runner.run_generation(generation, CONFIG, builder=builder, solver=solver)
        generation.refresh_from_db()
        prints.append(generation.config_snapshot["evaluation"]["fingerprint"])
    assert prints[0] == prints[1]

    generation.status = "running"
    generation.save(update_fields=["status"])
    runner.run_generation(generation, CONFIG, builder=builder, solver=solver)
    assert ScheduleSlot.objects.filter(generation=generation).count() == len(rows), "لا تضاعُف"


def test_worker_skips_a_generation_that_is_not_pending(known_good):
    from operations.scheduler_v2.tasks import generate_schedule_v2_task

    school, _ = known_good
    done = _generation(school, status="draft")
    assert generate_schedule_v2_task.run(str(done.pk)) == {"ok": False, "reason": "not_pending"}
    assert generate_schedule_v2_task.run("00000000-0000-0000-0000-000000000000")["ok"] is False


# ── الاعتماد: قدرة + بصمة + Audit ──────────────────────────────────────────


@pytest.fixture
def draft(known_good):
    school, rows = known_good
    builder, solver, _ = _fake("OPTIMAL", rows)
    generation = _generation(school)
    runner.run_generation(generation, CONFIG, builder=builder, solver=solver)
    generation.refresh_from_db()
    return school, generation


def test_approval_requires_the_capability(draft, monkeypatch):
    school, generation = draft
    monkeypatch.setattr("core.capabilities.has_capability", lambda user, key: False)
    with pytest.raises(runner.ApprovalRefusedError, match="قدرة"):
        runner.approve_v2(generation, user=UserFactory())
    generation.refresh_from_db()
    assert generation.status == "draft"


def test_approval_publishes_and_is_audited(draft, monkeypatch):
    school, generation = draft
    monkeypatch.setattr(
        "core.capabilities.has_capability", lambda user, key: key == "schedule.approve"
    )
    user = UserFactory()

    runner.approve_v2(generation, user=user)

    generation.refresh_from_db()
    assert generation.status == "approved"
    assert ScheduleSlot.objects.filter(generation=generation, is_active=True).exists()
    log = AuditLog.objects.filter(changes__event="schedule_v2_approved").get()
    assert log.changes["fingerprint"] == generation.config_snapshot["evaluation"]["fingerprint"]


def test_approval_refuses_a_draft_edited_after_acceptance(draft, monkeypatch):
    school, generation = draft
    monkeypatch.setattr("core.capabilities.has_capability", lambda user, key: True)
    ScheduleSlot.objects.filter(generation=generation).first().delete()
    with pytest.raises(runner.ApprovalRefusedError):
        runner.approve_v2(generation, user=UserFactory())


# ── أمر الإدارة ────────────────────────────────────────────────────────────


def test_dry_run_command_solves_and_evaluates_without_writing(known_good, monkeypatch):
    school, rows = known_good
    builder, solver, _ = _fake("OPTIMAL", rows)
    monkeypatch.setattr(runner, "default_builder", lambda: builder)
    monkeypatch.setattr(runner, "solve", lambda built, config, progress=None: solver(built, config))
    monkeypatch.setattr(runner, "default_objective", lambda: None)
    before = ScheduleGeneration.objects.count()

    out = StringIO()
    call_command(
        "generate_schedule_v2",
        "--dry-run",
        "--seed",
        "5",
        "--workers",
        "1",
        "--year",
        YEAR,
        stdout=out,
    )

    assert "OPTIMAL" in out.getvalue() and "مسودّةٌ مقبولة" in out.getvalue()
    assert "بذرة 5" in out.getvalue()
    assert ScheduleGeneration.objects.count() == before
    assert not ScheduleSlot.objects.filter(generation__isnull=False).exists()


def test_dry_run_command_without_model_is_a_clean_error(scene, monkeypatch):
    monkeypatch.setattr(runner, "_load_attr", lambda module, name: None)
    with pytest.raises(CommandError, match="لم يُدمج"):
        call_command("generate_schedule_v2", "--dry-run", "--year", YEAR)


# ── الحزمة المُقنَّعة ──────────────────────────────────────────────────────


def test_anonymized_fixture_flows_through_the_builder_contract():
    data = json.loads(FIXTURE.read_text(encoding="utf-8"))
    inputs = CpSatInputs(
        demand=[
            DemandRow(r["cls"], r["subj"], r["teacher"], r["elec"], r["n"]) for r in data["demand"]
        ],
        bell=data["bell"],
        class_band=data["class_band"],
    )
    seen = {}

    def builder(got):
        seen["total"] = got.total
        seen["classes"] = len(got.class_band)
        return SimpleNamespace(model=object())

    def objective(built, got):
        seen["objective"] = True

    def solver(built, config):
        return runner.SolveReport(
            "UNKNOWN", runner.VERDICTS["UNKNOWN"], config.seed, config.workers, 0.0
        )

    report = runner.solve_inputs(
        inputs, CONFIG, builder=builder, objective=objective, solver=solver
    )

    assert report.status == "UNKNOWN" and seen["objective"] is True
    assert seen["total"] == sum(r["n"] for r in data["demand"]) and seen["classes"] == 25


def test_real_solver_records_seed_workers_and_status_text():
    pytest.importorskip("ortools")
    from ortools.sat.python import cp_model

    model = cp_model.CpModel()
    x = model.NewIntVar(0, 3, "x")
    model.Maximize(x)
    built = SimpleNamespace(model=model, extract=lambda solver: [("c", "s", "t", 0, 1)])

    report = runner.solve(built, runner.SolverConfig(seed=3, workers=2, max_seconds=5))

    assert report.status == "OPTIMAL" and report.seed == 3 and report.workers == 2
    assert report.slots == [("c", "s", "t", 0, 1)] and report.objective == 3

    model2 = cp_model.CpModel()
    y = model2.NewIntVar(0, 1, "y")
    model2.Add(y >= 2)
    bad = runner.solve(SimpleNamespace(model=model2, extract=lambda s: []), CONFIG)
    assert bad.status == "INFEASIBLE" and bad.slots == []


def test_extract_slots_reads_the_core_x_contract():
    """عقدُ v2-core: x[(فهرسُ الصفّ، يوم، حصّة)] متغيّرٌ ثنائيّ؛ ما قيمته 1 يصير صفّاً بالمعرّفات."""
    demand = [DemandRow("C1", "S1", "T1", "", 2), DemandRow("C2", "S2", "T2", "", 1)]
    built = SimpleNamespace(
        inputs=CpSatInputs(demand=demand),
        x={(0, 0, 1): "a", (0, 0, 2): "b", (1, 3, 4): "c", (1, 3, 5): "d"},
    )
    solver = SimpleNamespace(Value=lambda var: 1 if var in ("a", "b", "c") else 0)

    assert runner.extract_slots(built, solver) == [
        ("C1", "S1", "T1", 0, 1),
        ("C1", "S1", "T1", 0, 2),
        ("C2", "S2", "T2", 3, 4),
    ]


# ── سجلُّ التقدّم والإيقاف المبكر ───────────────────────────────────────────


def test_tracker_publishes_gap_and_states_and_stop_flag_round_trips(scene):
    from operations.scheduler_v2 import progress

    generation = _generation(scene)
    tracker = progress.ProgressTracker(generation.pk, 120)
    assert tracker.snapshot()["state"] == "running" and tracker.snapshot()["gap_pct"] is None

    tracker.on_solution(objective=110.0, bound=100.0)
    snap = tracker.snapshot()
    assert snap["state"] == "feasible" and snap["gap_pct"] == 9.09 and snap["solutions"] == 1
    assert snap["remaining_s"] <= 120 and snap["done"] is False

    assert tracker.publish() is False
    assert progress.read_progress(generation)["objective"] == 110.0
    assert progress.request_stop(generation) is True
    assert tracker.publish() is True, "العاملُ يلتقط الطلبَ عند النشر التالي"
    assert progress.read_progress(generation)["stop_requested"] is True
    tracker.finish("stopped")
    final = progress.read_progress(generation)
    assert final["done"] is True and final["state_label"] == "أُوقف مبكّراً بأفضل حلّ"


def test_stop_is_refused_when_not_running(scene):
    from operations.scheduler_v2 import progress

    done = _generation(scene, status="draft")
    assert progress.request_stop(done) is False


def test_stopped_run_with_a_solution_keeps_the_best_and_labels_it_stopped(known_good):
    school, rows = known_good
    builder, _, _ = _fake("FEASIBLE", rows)
    generation = _generation(school)
    from operations.scheduler_v2 import progress

    tracker = progress.ProgressTracker(generation.pk, 60)
    tracker.stop_flag = True

    def solver(model, config):
        return runner.SolveReport("FEASIBLE", runner.VERDICTS["FEASIBLE"], 1, 1, 0.1, slots=rows)

    result = runner.run_generation(
        generation, CONFIG, builder=builder, solver=solver, progress=tracker
    )

    generation.refresh_from_db()
    assert result.ok and generation.status == "draft"
    assert progress.read_progress(generation)["state"] == "stopped"


def test_infeasible_run_ends_with_infeasible_progress_state(known_good):
    from operations.scheduler_v2 import progress

    school, _ = known_good
    builder, solver, _ = _fake("INFEASIBLE")
    generation = _generation(school)
    runner.run_generation(generation, CONFIG, builder=builder, solver=solver)
    snap = progress.read_progress(generation)
    assert snap["state"] == "infeasible" and snap["done"] is True and snap["error"]


# ── صفُّ الشعبة لـHC17 ─────────────────────────────────────────────────────


def test_adapter_carries_the_class_grade_and_default_options_pass_it_on(monkeypatch):
    from dataclasses import dataclass, field

    from operations.cpsat_adapter import build_inputs
    from operations.scheduler import Task

    task = Task(
        class_id="C1",
        class_name="11/1",
        subject_id="S1",
        subject_name="م",
        subject_code="M",
        teacher_id="T1",
        teacher_name="ع",
        weekly_periods=3,
        level_type="sec",
        grade="G11",
    )
    inputs = build_inputs([task])
    assert inputs.class_grade == {"C1": "G11"}

    @dataclass(frozen=True)
    class FakeOptions:
        class_grade: dict = field(default_factory=dict)

    monkeypatch.setattr(runner, "_load_attr", lambda module, name: FakeOptions)
    assert runner.default_options(inputs).class_grade == {"C1": "G11"}

    @dataclass(frozen=True)
    class OldOptions:
        first_cap: int = 2

    monkeypatch.setattr(runner, "_load_attr", lambda module, name: OldOptions)
    assert runner.default_options(inputs) == OldOptions()


def test_options_from_relaxations_maps_owner_decisions_and_rejects_unknown_keys():
    """ملفُّ --relaxations: يحوّل قراراتِ المالك إلى حقول ModelOptions، ويرفض مفتاحاً مجهولاً (لا تخفيفَ صامت)."""
    out = runner.options_from_relaxations(
        {
            "touch_relaxed": ["T1"],
            "run_cap": 2,
            "first_cap_override": {"T2": 4},
            "no_6_7": True,
            "triples_by_number": True,
        }
    )
    assert out == {
        "touch_relaxed": frozenset({"T1"}),
        "touch_relaxed_run_cap": 2,
        "first_cap_override": (("T2", 4),),
        "no_6_7": True,
        "triples_by_number": True,
    }
    with pytest.raises(runner.RunnerError):
        runner.options_from_relaxations({"bogus": 1})

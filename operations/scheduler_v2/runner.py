"""runner.py — مشغِّلُ التوليد V2: يبني النموذجَ ويحلّه ويمرّر الناتجَ على المُقيِّم المستقلّ ثمّ يكتبه مسودّةً (V2-S4/S5).

التسلسل (ADR-0008 §3): مدخلاتٌ من الحقيقة الحيّة ← `build_model` (v2-core) ← هدفٌ (v2-objective) ← حلٌّ بشروط
إعادة الإنتاج ← **`evaluate_slots` المستقلّ** ← مسودّةٌ غيرُ منشورة. ولا تُكتب حصّةٌ في القاعدة قبل أن يقبل المُقيِّمُ
ناتجَ الحلّال بلا مخالفةٍ صلبة ولا حصّةٍ بلا موضع؛ فالمسودّةُ التي تُعرض مقبولةٌ سلفاً.

العقدُ مع الجلستين الأخريين (Protocol مؤقّت إلى أن تظهر ملفّاتهما):
  · `operations.scheduler_v2.model.build_model(inputs: CpSatInputs) -> BuiltModel`
  · `BuiltModel.model` و`BuiltModel.inputs` و`BuiltModel.x[(فهرسُ الصفّ، يوم، حصّة)]` (ثُبّت في 94ea34d7)
  · `operations.scheduler_v2.objective.add_objective(built, inputs) -> None` (اختياريّ: غيابُه يُسجَّل بلا هدف)
"""

from __future__ import annotations

import logging
import time
import zlib
from collections.abc import Callable
from contextlib import contextmanager
from dataclasses import dataclass, field
from importlib import import_module
from types import SimpleNamespace
from typing import Any, Protocol

from django.db import connection, transaction
from django.utils import timezone

from operations.cpsat_adapter import CpSatInputs, build_inputs
from operations.schedule_evaluator import VERDICTS, Evaluation, evaluate_slots

logger = logging.getLogger(__name__)

ENGINE = "cpsat_v2"
#: بذرةٌ ثابتةٌ افتراضيّاً (ADR §3.5) وعمّالٌ مثبَّتون — يُسجَّلان مع كلّ توليد.
DEFAULT_SEED = 20261011
DEFAULT_WORKERS = 8
DEFAULT_MAX_SECONDS = 600
#: مساحةُ القفل الاستشاريّ (مع معرّف المدرسة) — حلٌّ متزامنٌ واحدٌ لكلّ مدرسة.
_LOCK_NAMESPACE = 0x5632

SlotRow = tuple[str, str, str, int, int]


class BuiltModel(Protocol):
    model: Any
    inputs: CpSatInputs
    x: dict


ModelBuilder = Callable[[CpSatInputs], BuiltModel]
ObjectiveAdder = Callable[[BuiltModel, CpSatInputs], None]


class RunnerError(Exception):
    """فشلٌ يُقال للمستخدم كما هو."""


class ContractMissingError(RunnerError):
    """ملفُّ النموذج (v2-core) لم يصل بعد."""


class SchoolBusyError(RunnerError):
    """حلٌّ آخرُ جارٍ لهذه المدرسة."""


class ApprovalRefusedError(RunnerError):
    """اعتمادٌ مرفوض: القدرةُ أو القبولُ أو البصمة."""


@dataclass(frozen=True)
class SolverConfig:
    seed: int = DEFAULT_SEED
    workers: int = DEFAULT_WORKERS
    max_seconds: float = DEFAULT_MAX_SECONDS


@dataclass
class SolveReport:
    status: str  # نصٌّ: OPTIMAL/FEASIBLE/INFEASIBLE/UNKNOWN
    verdict: str
    seed: int
    workers: int
    seconds: float
    objective: float | None = None
    slots: list[SlotRow] = field(default_factory=list)

    def solver_dict(self) -> dict[str, Any]:
        """الشكلُ الذي يقرؤه المُقيِّم: الحالةُ والبذرةُ والعمّالُ والزمن."""
        return {
            "status": self.status,
            "seed": self.seed,
            "workers": self.workers,
            "seconds": round(self.seconds, 2),
        }


@dataclass
class RunResult:
    ok: bool
    report: SolveReport | None
    evaluation: Evaluation | None
    message: str = ""
    reason: str = ""  # infeasible | timeout | rejected | busy | no_model | ok


# ───────────────────────── العقد والحلّال ─────────────────────────


def _load_attr(module: str, name: str) -> Any:
    try:
        return getattr(import_module(module), name)
    except (ImportError, AttributeError):
        return None


def default_builder() -> ModelBuilder:
    builder = _load_attr("operations.scheduler_v2.model", "build_model")
    if builder is None:
        raise ContractMissingError("نموذجُ V2 (operations/scheduler_v2/model.py) لم يُدمج بعد")
    return builder


def default_objective() -> ObjectiveAdder | None:
    return _load_attr("operations.scheduler_v2.objective", "add_objective")


def _status_name(cp_model: Any, code: int) -> str:
    if code == cp_model.MODEL_INVALID:
        raise RunnerError("نموذجٌ غيرُ صالح (MODEL_INVALID) — عطبٌ في الترميز لا في البيانات")
    names = {
        cp_model.OPTIMAL: "OPTIMAL",
        cp_model.FEASIBLE: "FEASIBLE",
        cp_model.INFEASIBLE: "INFEASIBLE",
        cp_model.UNKNOWN: "UNKNOWN",
    }
    return names.get(code, "UNKNOWN")


def extract_slots(built: Any, solver: Any) -> list[SlotRow]:
    """صفوفُ (شعبة، مادّة، معلّم، يوم، حصّة) من `built.x[(فهرسُ الصفّ، يوم، حصّة)]` (عقدُ v2-core).

    ويبقى `built.extract` مقدَّماً إن وُجد (للمزيَّفات). المفتاحُ يُحلّ إلى `built.inputs.demand[فهرس]`.
    """
    custom = getattr(built, "extract", None)
    if custom is not None:
        return [tuple(row) for row in custom(solver)]  # type: ignore[misc]
    demand = built.inputs.demand
    rows = []
    for (index, day, period), var in sorted(built.x.items()):
        if solver.Value(var):
            row = demand[index]
            rows.append((row.cls, row.subj, row.teacher, day, period))
    return rows


def solve(built: BuiltModel, config: SolverConfig) -> SolveReport:
    """يحلّ بإعدادٍ مثبَّت: بذرةٌ، عمّالٌ، سقفُ زمنٍ جداريّ. ويسجّل الحالةَ نصّاً (ADR §3.4/§3.5)."""
    from ortools.sat.python import cp_model

    solver = cp_model.CpSolver()
    params = solver.parameters
    params.random_seed = config.seed
    params.num_workers = config.workers
    params.max_time_in_seconds = float(config.max_seconds)
    # أقربُ ما يتيحه الحلّالُ إلى الحتميّة متعدّدَ العمّال.
    params.interleave_search = config.workers > 1
    started = time.monotonic()
    code = solver.Solve(built.model)
    seconds = time.monotonic() - started
    status = _status_name(cp_model, code)
    slots: list[SlotRow] = []
    objective = None
    if status in ("OPTIMAL", "FEASIBLE"):
        slots = extract_slots(built, solver)
        objective = solver.ObjectiveValue()
    return SolveReport(
        status=status,
        verdict=VERDICTS[status],
        seed=config.seed,
        workers=config.workers,
        seconds=seconds,
        objective=objective,
        slots=slots,
    )


Solver = Callable[[BuiltModel, SolverConfig], SolveReport]


# ───────────────────────── القفل ─────────────────────────


@contextmanager
def school_solve_lock(school_id: Any):
    """قفلٌ استشاريّ على مستوى الجلسة (لا المعاملة: الحلُّ دقائقُ) — حلٌّ واحدٌ لكلّ مدرسة."""
    key = zlib.crc32(str(school_id).encode()) & 0x7FFFFFFF
    with connection.cursor() as cursor:
        cursor.execute("SELECT pg_try_advisory_lock(%s, %s)", [_LOCK_NAMESPACE, key])
        if not cursor.fetchone()[0]:
            raise SchoolBusyError("حلٌّ آخرُ جارٍ لهذه المدرسة — انتظر انتهاءَه")
    try:
        yield
    finally:
        with connection.cursor() as cursor:
            cursor.execute("SELECT pg_advisory_unlock(%s, %s)", [_LOCK_NAMESPACE, key])


# ───────────────────────── المدخلات والتشغيل ─────────────────────────


def load_inputs(school: Any, academic_year: str) -> CpSatInputs:
    """مدخلاتُ النموذج من الحقيقة الحيّة نفسِها التي يقرؤها المولّدُ الحاليّ — السياسةُ تُقرأ مرّةً هنا (ADR §3.2)."""
    from operations.scheduler import bell_lookup, build_tasks
    from operations.scheduler import load_inputs as load_scheduler_inputs

    tasks = build_tasks(school, academic_year)
    prefs_qs, _preferences, blocked = load_scheduler_inputs(school, academic_year)
    return build_inputs(tasks, blocked, prefs_qs, bell_lookup(school))


def solve_inputs(
    inputs: CpSatInputs,
    config: SolverConfig,
    *,
    builder: ModelBuilder | None = None,
    objective: ObjectiveAdder | None = None,
    solver: Solver | None = None,
) -> SolveReport:
    built = (builder or default_builder())(inputs)
    add_objective = objective if objective is not None else default_objective()
    if add_objective is not None:
        add_objective(built, inputs)
    return (solver or solve)(built, config)


def evaluate_report(school: Any, academic_year: str, report: SolveReport) -> Evaluation:
    """المُقيِّمُ المستقلّ على ناتج الحلّال بالمعرّفات — لا يقرأ عدّاداً من الباني."""
    rows = [
        SimpleNamespace(
            class_group_id=c, subject_id=s, teacher_id=t, day_of_week=d, period_number=p
        )
        for c, s, t, d, p in report.slots
    ]
    return evaluate_slots(school, academic_year, rows, report.solver_dict())


def _elective_labels(inputs: CpSatInputs, slots: list[SlotRow]) -> dict[SlotRow, str]:
    """وسمُ الساكن في الخانة المنقسمة (كما في `_member_labels`): يميّز صفوفَ الخانة الواحدة فلا يرفضها القيدُ الفريد."""
    cells: dict[tuple, list[SlotRow]] = {}
    for row in slots:
        cells.setdefault((row[0], row[3], row[4]), []).append(row)
    labels: dict[SlotRow, str] = {}
    for rows in cells.values():
        if len(rows) < 2:
            continue
        names = [inputs.subject_names.get(r[1], r[1]) for r in rows]
        unique = len(set(names)) == len(names)
        for index, (row, name) in enumerate(zip(rows, names, strict=True)):
            labels[row] = name[:40] if unique else f"{index + 1}·{name}"[:40]
    return labels


def run(
    school: Any,
    academic_year: str,
    config: SolverConfig,
    *,
    inputs: CpSatInputs | None = None,
    builder: ModelBuilder | None = None,
    objective: ObjectiveAdder | None = None,
    solver: Solver | None = None,
) -> tuple[RunResult, CpSatInputs]:
    """حلٌّ + تقييمٌ مستقلّ بلا كتابة. يميّز INFEASIBLE (برهان) عن UNKNOWN/المهلة وعن رفض المُقيِّم."""
    inputs = inputs if inputs is not None else load_inputs(school, academic_year)
    with school_solve_lock(school.pk):
        report = solve_inputs(inputs, config, builder=builder, objective=objective, solver=solver)
    if report.status == "INFEASIBLE":
        message = "مستحيلٌ بالبرهان (INFEASIBLE): القيودُ متعارضة"
        return RunResult(False, report, None, message, "infeasible"), inputs
    if not report.slots:
        message = f"انقضت المهلةُ ({config.max_seconds:g}ث) بلا حلٍّ (UNKNOWN) — ضيقُ وقتٍ لا استحالة"
        return RunResult(False, report, None, message, "timeout"), inputs
    evaluation = evaluate_report(school, academic_year, report)
    if not evaluation.accepted:
        hard = (
            ", ".join(f"{k}={v}" for k, v in sorted(evaluation.hard_breaches.items())) or "لا شيء"
        )
        message = (
            f"رفض المُقيِّمُ المستقلّ ناتجَ الحلّال: InfeasibilityValue={evaluation.infeasibility_value}"
            f"، مخالفاتٌ صلبة={evaluation.hard_total} ({hard})، خاناتٌ بلا إسناد={evaluation.orphan_cells}"
        )
        return RunResult(False, report, evaluation, message, "rejected"), inputs
    return RunResult(True, report, evaluation, "", "ok"), inputs


def persist_draft(generation: Any, result: RunResult, inputs: CpSatInputs, elapsed_ms: int) -> int:
    """يكتب مسودّةً غيرَ منشورة (`is_active=False`) بأرقام الحصص وأوقاتِ الجرس نفسِها — بعد قبول المُقيِّم فقط."""
    from operations.models import ScheduleGeneration, ScheduleSlot
    from operations.scheduler import bell_lookup

    if not (result.ok and result.report and result.evaluation):
        raise RunnerError("لا تُكتب مسودّةٌ لم يقبلها المُقيِّم")
    school, year = generation.school, generation.academic_year
    get_time = bell_lookup(school)
    labels = _elective_labels(inputs, result.report.slots)
    rows = []
    for row in sorted(result.report.slots):
        cls, subj, teacher, day, period = row
        start, end = get_time(day, period, inputs.class_band.get(cls) or None)
        rows.append(
            ScheduleSlot(
                school=school,
                teacher_id=teacher,
                class_group_id=cls,
                subject_id=subj,
                day_of_week=day,
                period_number=period,
                start_time=start,
                end_time=end,
                academic_year=year,
                elective_group=labels.get(row, ""),
                is_active=False,
                generation=generation,
            )
        )
    snapshot = {
        "engine": ENGINE,
        "solver": result.report.solver_dict(),
        "verdict": result.report.verdict,
        "evaluation": result.evaluation.as_dict(),
    }
    with transaction.atomic():
        locked = ScheduleGeneration.objects.select_for_update().get(pk=generation.pk)
        if locked.status != "running":  # أُوقف أو حُذف في الأثناء: لا نكتب فوقه
            return 0
        ScheduleSlot.objects.filter(generation=locked).delete()  # idempotent: إعادةٌ تُبدّل لا تُضاعف
        ScheduleSlot.objects.bulk_create(rows, batch_size=500)
        locked.status = "draft"
        locked.hard_violations = 0
        locked.soft_violations = result.evaluation.soft_counts
        locked.total_slots_created = len(rows)
        locked.generation_time_ms = elapsed_ms
        locked.config_snapshot = snapshot
        locked.finished_at = timezone.now()
        locked.save()
    return len(rows)


def fail_generation(generation: Any, result: RunResult) -> None:
    """يُسجَّل الفشلُ نصّاً يميّز السببَ، وحالةُ الحلّال والبذرةُ في اللقطة لتبقى قابلةً للتتبّع."""
    from operations.models import ScheduleGeneration

    snapshot: dict[str, Any] = {"engine": ENGINE, "reason": result.reason}
    if result.report is not None:
        snapshot["solver"] = result.report.solver_dict()
        snapshot["verdict"] = result.report.verdict
    if result.evaluation is not None:
        snapshot["evaluation"] = result.evaluation.as_dict()
    ScheduleGeneration.objects.filter(pk=generation.pk, status="running").update(
        status="failed",
        error_message=result.message[:2000],
        config_snapshot=snapshot,
        finished_at=timezone.now(),
    )


def run_generation(generation: Any, config: SolverConfig, **kwargs: Any) -> RunResult:
    """يشغّل توليداً قائماً (صفٌّ `running`) ويكتب مصيرَه: مسودّةٌ مقبولة أو فشلٌ مفسَّر."""
    started = time.monotonic()
    inputs = None
    try:
        result, inputs = run(generation.school, generation.academic_year, config, **kwargs)
    except SchoolBusyError as error:
        result = RunResult(False, None, None, str(error), "busy")
    except ContractMissingError as error:
        result = RunResult(False, None, None, str(error), "no_model")
    if not result.ok:
        fail_generation(generation, result)
        return result
    persist_draft(generation, result, inputs, int((time.monotonic() - started) * 1000))
    return result


# ───────────────────────── البوّابة: العرضُ والاعتماد ─────────────────────────


def is_displayable(generation: Any) -> bool:
    """لا تُعرض مسودّةُ V2 قبل أن يقبلها المُقيِّم: اللقطةُ تحمل قبولَه، ولا مسودّةَ تُكتب دونه."""
    snap = generation.config_snapshot or {}
    if snap.get("engine") != ENGINE:
        return True  # ليست من V2: خارج هذه البوّابة
    return generation.status == "draft" and bool((snap.get("evaluation") or {}).get("accepted"))


def approve_v2(generation: Any, *, user: Any, request: Any = None) -> dict:
    """اعتمادُ مسودّة V2: بقدرة `schedule.approve`، وبإعادة تقييمٍ مستقلّةٍ تطابق بصمةَ المقبول، ومسجَّلٌ في Audit."""
    from core.capabilities import has_capability
    from core.models.audit import AuditLog
    from operations.schedule_evaluator import generation_slots
    from operations.services.schedule import ScheduleService

    if not has_capability(user, "schedule.approve"):
        raise ApprovalRefusedError("لا تملك قدرة اعتماد الجدول")
    if generation.status != "draft" or not is_displayable(generation):
        raise ApprovalRefusedError("ليست مسودّةً مقبولةً من المُقيِّم — لا تُعتمد")
    snap = generation.config_snapshot or {}
    fresh = evaluate_slots(
        generation.school,
        generation.academic_year,
        generation_slots(generation),
        snap.get("solver"),
    )
    if not fresh.accepted or fresh.fingerprint != (snap.get("evaluation") or {}).get("fingerprint"):
        raise ApprovalRefusedError("تغيّرت المسودّةُ بعد قبولها أو لم تعد مقبولة — أعد التوليد")
    result = ScheduleService.approve_generation(generation, acknowledged=False)
    AuditLog.log(
        user=user,
        action="update",
        model_name="other",
        object_id=generation.pk,
        object_repr=f"اعتمادُ جدول V2 {generation.academic_year}",
        changes={
            "event": "schedule_v2_approved",
            "fingerprint": fresh.fingerprint,
            "solver": snap.get("solver"),
            "objective_value": fresh.objective_value,
        },
        school=generation.school,
        request=request,
    )
    return result

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
#: HC14 وHC16B مفعَّلان افتراضاً ويقيسهما الحلّالُ UNKNOWN عند 90ث، فالسقفُ طويل (30 دقيقة) لا إيقافٌ لهما.
DEFAULT_MAX_SECONDS = 1800
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
    #: تخفيفاتٌ معلَنةٌ بقرار المالك تُمرَّر لخيارات النموذج (انظر `options_from_relaxations`)؛ فارغٌ = الصرامة.
    relaxations: tuple[tuple[str, Any], ...] = ()
    #: الهدفُ المعجميّ المتتالي (متعذّرات ← مخالفات ← درجة) بدل هدفٍ واحدٍ موزون؛ يعمل متى سُجّلت طبقاتٌ ≥ 2.
    lexicographic: bool = True
    #: يفتح فجوةَ الطلب في النموذج (يُفعَّل معه طبقةُ المتعذّرات)؛ افتراضُه الصرامة: مساواةٌ صلبة.
    allow_unplaced: bool = False


def options_from_relaxations(spec: dict[str, Any] | None) -> dict[str, Any]:
    """يحوّل ملفَّ `--relaxations` إلى حقول `ModelOptions`: touch_relaxed وrun_cap وfirst_cap_override وno_6_7 والثلاثيات.

    الشكل: {"touch_relaxed": ["T..."], "run_cap": 2, "first_cap_override": {"T...": 4}, "no_6_7": true,
    "triples_by_number": true}. مفتاحٌ مجهولٌ يُرفض (لا تخفيفَ صامت).
    """
    spec = dict(spec or {})
    out: dict[str, Any] = {}
    if "touch_relaxed" in spec:
        out["touch_relaxed"] = frozenset(spec.pop("touch_relaxed"))
    if "run_cap" in spec:
        out["touch_relaxed_run_cap"] = int(spec.pop("run_cap"))
    if "first_cap_override" in spec:
        out["first_cap_override"] = tuple(sorted(dict(spec.pop("first_cap_override")).items()))
    for flag in ("no_6_7", "triples_by_number"):
        if flag in spec:
            out[flag] = bool(spec.pop(flag))
    if spec:
        raise RunnerError(f"مفاتيح تخفيفٍ غير معروفة: {sorted(spec)}")
    return out


def with_admin_first_caps(config: SolverConfig, school: Any, academic_year: str) -> SolverConfig:
    """يضمّ سقوفَ الأولى المقرَّرةَ إدارياً (الأدمن) إلى `first_cap_override`؛ والأعلى يغلب ملفَّ التخفيف.

    المصدرُ بعد W-20261010-033 هو الحقل `TeacherPreference.max_first_periods`؛ وملفُّ `--relaxations` يبقى
    خياراً لتشغيلٍ بعينه فوق الأساس لا بديلاً عنه.
    """
    from dataclasses import replace

    from operations.schedule_evaluator import admin_first_caps

    stored = admin_first_caps(school, academic_year)
    if not stored:
        return config
    spec = dict(config.relaxations)
    merged = dict(spec.get("first_cap_override") or {})
    for teacher, cap in stored.items():
        merged[teacher] = max(cap, merged.get(teacher, 0))
    spec["first_cap_override"] = merged
    return replace(config, relaxations=tuple(sorted(spec.items(), key=lambda kv: kv[0])))


@dataclass
class SolveReport:
    status: str  # نصٌّ: OPTIMAL/FEASIBLE/INFEASIBLE/UNKNOWN
    verdict: str
    seed: int
    workers: int
    seconds: float
    objective: float | None = None
    slots: list[SlotRow] = field(default_factory=list)
    #: تخفيفُ HC5 المعلَن فعلاً ({معلّم ← أقصى تتابع}) كما يقرؤه المُقيِّم؛ يملؤه `solve_inputs` من BuiltModel.
    relaxations: dict[str, int] = field(default_factory=dict)
    #: تخفيفُ HC22 المعلَن فعلاً ({معلّم ← سقف الأولى}) كما يقرؤه المُقيِّم (W-20261003-043).
    first_caps: dict[str, int] = field(default_factory=dict)
    #: قيمُ الطبقات المعجميّة في الحلّ النهائيّ بالاسم ({"unplaced": …}) — فارغٌ حين لا طبقات.
    layers: dict[str, int] = field(default_factory=dict)
    #: حصصٌ لم توضع (طبقة المتعذّرات). >0 ⇒ جدولٌ ناقصٌ لا يصلح للتوليد حتى يعالجه المالك.
    unplaced: int = 0

    def solver_dict(self) -> dict[str, Any]:
        """الشكلُ الذي يقرؤه المُقيِّم: الحالةُ والبذرةُ والعمّالُ والزمن."""
        return {
            "status": self.status,
            "seed": self.seed,
            "workers": self.workers,
            "seconds": round(self.seconds, 2),
        }

    def lexicographic_dict(self) -> dict[str, Any]:
        """طبقاتُ الهدف المعجميّ للّقطة (خارج `solver_dict` الذي يحرس المُقيِّمُ مفاتيحه)."""
        return {"layers": dict(self.layers), "unplaced": self.unplaced}


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


def default_options(inputs: CpSatInputs, extra: dict[str, Any] | None = None) -> Any:
    """`ModelOptions` للمشغّل: صفوفُ الشعب لـHC17، ولا يُوقَف قيدٌ (HC14/HC16B مفعَّلان).

    يُمرَّر `class_grade` إن كان حقلاً في `ModelOptions` (ملفُّ v2-core)؛ وإلّا يُترك فلا يسقط المشغّل بحقلٍ لم يصل.
    """
    from dataclasses import fields

    model_options = _load_attr("operations.scheduler_v2.model", "ModelOptions")
    if model_options is None:
        return None
    kwargs = {}
    if "class_grade" in {f.name for f in fields(model_options)}:
        kwargs["class_grade"] = dict(inputs.class_grade)
    kwargs.update(extra or {})
    return model_options(**kwargs)


def default_objective() -> ObjectiveAdder | None:
    """يضيف الهدفَ المرن (v2-objective): `build_objective` ثمّ `add_soft_terms` (v2-core). غيابُهما ⇒ بلا هدف."""
    build_objective = _load_attr("operations.scheduler_v2.objective", "build_objective")
    add_soft_terms = _load_attr("operations.scheduler_v2.model", "add_soft_terms")
    if build_objective is None or add_soft_terms is None:
        return None

    def add(built: BuiltModel, inputs: CpSatInputs) -> None:
        objective = build_objective(built, inputs.subject_pedagogy)
        add_soft_terms(built, objective.as_terms())
        add_layers = _load_attr("operations.scheduler_v2.model", "add_layers")
        if add_layers is not None and hasattr(objective, "layers"):
            add_layers(built, objective.layers(built))

    return add


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


def _run_stage(
    built: BuiltModel,
    config: SolverConfig,
    progress: Any,
    max_seconds: float,
    report_progress: bool,
) -> tuple[Any, int, float]:
    """حلٌّ واحدٌ بإعدادٍ مثبَّت: (الحلّال، رمزُ الحالة، الثواني)."""
    from ortools.sat.python import cp_model

    solver = cp_model.CpSolver()
    params = solver.parameters
    params.random_seed = config.seed
    params.num_workers = config.workers
    params.max_time_in_seconds = float(max_seconds)
    # أقربُ ما يتيحه الحلّالُ إلى الحتميّة متعدّدَ العمّال.
    params.interleave_search = False

    callback = None
    ticker = None
    if progress is not None:
        from .progress import Ticker

        if report_progress:

            class _Callback(cp_model.CpSolverSolutionCallback):
                def on_solution_callback(self) -> None:
                    progress.on_solution(self.ObjectiveValue(), self.BestObjectiveBound())

            callback = _Callback()
        ticker = Ticker(progress, solver.StopSearch)
        ticker.start()
    started = time.monotonic()
    try:
        code = solver.Solve(built.model, callback) if callback else solver.Solve(built.model)
    finally:
        if ticker is not None:
            ticker.stop()
    return solver, code, time.monotonic() - started


def _layers_of(built: BuiltModel) -> list[tuple[str, Any]]:
    """طبقاتُ الهدف الفعليّة (تُسقَط الثابتةُ صفراً: طبقةُ المتعذّرات بلا فجوة)."""
    return [(n, e) for n, e in getattr(built, "layers", []) if not isinstance(e, int)]


def _probe_full_placement(
    built: BuiltModel, config: SolverConfig, progress: Any, seconds: float
) -> Any:
    """جسٌّ بلا هدف: هل يوجد جدولٌ بلا متعذّرات؟ يُرجع حلّالَه إن وُجد وإلّا None.

    طبقةُ المتعذّرات لو صُغِّرت وحدَها بلا توجيهٍ ربّما وقفت عند عددٍ لا صفر (قيس 4 على الحزمة المقنَّعة في
    100ث بينما الحلُّ الكاملُ موجود) ثم ثبّتها التاليةُ سقفاً. فيُجَسّ الصفرُ أوّلاً على نسخةٍ من النموذج
    بلا هدفٍ (جدوى أسهل)؛ وُجد ⇒ يُثبَّت صفراً ويُبدأ منه، ولم يوجد ⇒ تُصغَّر الطبقةُ بالتتابع العاديّ.
    """
    from types import SimpleNamespace

    from ortools.sat.python import cp_model

    probe = built.model.clone()
    probe.clear_objective()
    for key, var in built.vars.items():
        if key[0] == "unplaced":
            probe.Add(probe.get_int_var_from_proto_index(var.index) == 0)
    solver, code, _secs = _run_stage(SimpleNamespace(model=probe), config, progress, seconds, False)
    return solver if _status_name(cp_model, code) in ("OPTIMAL", "FEASIBLE") else None


def _solve_layers(
    built: BuiltModel, config: SolverConfig, progress: Any, layers: list[tuple[str, Any]]
) -> tuple[Any, str, float, dict[str, int], float]:
    """الحلُّ المعجميّ المتتالي: تُصغَّر كلُّ طبقةٍ بتثبيت قيمة ما فوقها، فلا تُضحَّى عليا بدنيا.

    تقسيمُ الزمن: ما بقي ÷ الطبقات الباقية. والمُثبَّت بعد طبقةٍ OPTIMAL مساواةٌ، وبعد FEASIBLE سقف
    (≤). وتبدأ كلُّ طبقةٍ بتلميح الحلّ السابق. طلبُ الإيقاف المبكّر يُبقي أفضلَ ما وُجد ويقطع الباقي.
    الإرجاع: (حلّالُ آخرِ حلٍّ، الحالة، الثواني، قيمُ الطبقات، قيمةُ الهدف الأخيرة).
    """
    from ortools.sat.python import cp_model

    started = time.monotonic()
    best = None
    all_optimal = True
    values: dict[str, int] = {}
    pending = list(layers)
    if pending[0][0] == "unplaced":
        probe = _probe_full_placement(built, config, progress, float(config.max_seconds) * 0.4)
        if probe is not None:  # جدولٌ كاملٌ موجود: الصفرُ مثبَّتٌ ولا تُصغَّر الطبقةُ الأولى
            built.model.Add(pending[0][1] == 0)
            best = probe
            pending = pending[1:]
    stage_total = len(pending)
    for idx, (name, expr) in enumerate(pending):
        remaining = max(0.5, float(config.max_seconds) - (time.monotonic() - started))
        stage_seconds = remaining / (stage_total - idx)
        built.model.ClearObjective()
        built.model.Minimize(expr)
        if best is not None:
            built.model.ClearHints()
            for var in built.x.values():
                built.model.AddHint(var, best.Value(var))
        last = idx == stage_total - 1
        solver, code, _secs = _run_stage(built, config, progress, stage_seconds, last)
        status = _status_name(cp_model, code)
        if status not in ("OPTIMAL", "FEASIBLE"):
            if best is None:  # الطبقةُ الأولى بلا حلّ: INFEASIBLE أو UNKNOWN كما هي
                return None, status, time.monotonic() - started, {}, 0.0
            all_optimal = False  # لم تجد الطبقةُ الأدنى شيئاً في وقتها: يبقى حلُّ ما فوقها
            break
        best = solver
        values[name] = int(round(solver.Value(expr)))
        all_optimal = all_optimal and status == "OPTIMAL"
        if not last:
            if status == "OPTIMAL":
                built.model.Add(expr == values[name])
            else:
                built.model.Add(expr <= values[name])
        if progress is not None and getattr(progress, "stop_flag", False):
            all_optimal = False
            break
    for name, expr in layers:  # قيمُ كلّ الطبقات في الحلّ الأخير (ما لم تُحلّ منها يُقاس لا يُقدَّر)
        values[name] = int(round(best.Value(expr)))
    objective = float(values[layers[-1][0]])
    seconds = time.monotonic() - started
    return best, "OPTIMAL" if all_optimal else "FEASIBLE", seconds, values, objective


def solve(built: BuiltModel, config: SolverConfig, progress: Any = None) -> SolveReport:
    """يحلّ بإعدادٍ مثبَّت: بذرةٌ، عمّالٌ، سقفُ زمنٍ جداريّ. ويسجّل الحالةَ نصّاً (ADR §3.4/§3.5).

    ومع `progress` (ProgressTracker) يُنشر التقدّمُ عند كلّ حلٍّ وكلَّ ثانية، ويوقف طلبُ الإيقاف البحثَ
    فيُبقي أفضلَ حلّ (الحالةُ FEASIBLE). ومع طبقاتٍ ≥ 2 في الباني وconfig.lexicographic يُحلّ متتالياً.
    """
    from ortools.sat.python import cp_model

    layers = _layers_of(built) if config.lexicographic else []
    layer_values: dict[str, int] = {}
    if len(layers) >= 2:
        solver, status, seconds, layer_values, final_objective = _solve_layers(
            built, config, progress, layers
        )
    else:
        solver, code, seconds = _run_stage(built, config, progress, config.max_seconds, True)
        status = _status_name(cp_model, code)
        final_objective = None
    slots: list[SlotRow] = []
    objective = None
    if status in ("OPTIMAL", "FEASIBLE"):
        slots = extract_slots(built, solver)
        objective = solver.ObjectiveValue() if final_objective is None else final_objective
        if progress is not None:
            progress.on_solution(objective, solver.BestObjectiveBound())
    return SolveReport(
        status=status,
        verdict=VERDICTS[status],
        seed=config.seed,
        workers=config.workers,
        seconds=seconds,
        objective=objective,
        slots=slots,
        layers=layer_values,
        unplaced=layer_values.get("unplaced", 0),
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
    from operations.scheduling_inputs import bell_lookup, build_tasks
    from operations.scheduling_inputs import load_inputs as load_scheduler_inputs

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
    progress: Any = None,
) -> SolveReport:
    if builder is None:
        extra = options_from_relaxations(dict(config.relaxations))
        if config.allow_unplaced:
            extra["allow_unplaced"] = True
        options = default_options(inputs, extra)
        built = (
            default_builder()(inputs, options) if options is not None else default_builder()(inputs)
        )
    else:
        built = builder(inputs)
    add_objective = objective if objective is not None else default_objective()
    if add_objective is not None:
        add_objective(built, inputs)
    report = solve(built, config, progress) if solver is None else solver(built, config)
    report.relaxations = {
        r["teacher"]: int(str(r["relaxed"]).rsplit("_", 1)[-1])
        for r in getattr(built, "relaxations", [])
        if r.get("code") == "HC5"
    }
    report.first_caps = {
        r["teacher"]: int(str(r["relaxed"]).rsplit("_", 1)[-1])
        for r in getattr(built, "relaxations", [])
        if r.get("code") == "HC22"
    }
    return report


def evaluate_report(school: Any, academic_year: str, report: SolveReport) -> Evaluation:
    """المُقيِّمُ المستقلّ على ناتج الحلّال بالمعرّفات — لا يقرأ عدّاداً من الباني."""
    rows = [
        SimpleNamespace(
            class_group_id=c, subject_id=s, teacher_id=t, day_of_week=d, period_number=p
        )
        for c, s, t, d, p in report.slots
    ]
    return evaluate_slots(
        school,
        academic_year,
        rows,
        report.solver_dict(),
        report.relaxations or None,
        report.first_caps or None,
    )


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
    progress: Any = None,
) -> tuple[RunResult, CpSatInputs]:
    """حلٌّ + تقييمٌ مستقلّ بلا كتابة. يميّز INFEASIBLE (برهان) عن UNKNOWN/المهلة وعن رفض المُقيِّم."""
    inputs = inputs if inputs is not None else load_inputs(school, academic_year)
    config = with_admin_first_caps(config, school, academic_year)
    with school_solve_lock(school.pk):
        report = solve_inputs(
            inputs, config, builder=builder, objective=objective, solver=solver, progress=progress
        )
    if report.status == "INFEASIBLE":
        message = "مستحيلٌ بالبرهان (INFEASIBLE): القيودُ متعارضة"
        return RunResult(False, report, None, message, "infeasible"), inputs
    if not report.slots:
        message = f"انقضت المهلةُ ({config.max_seconds:g}ث) بلا حلٍّ (UNKNOWN) — ضيقُ وقتٍ لا استحالة"
        return RunResult(False, report, None, message, "timeout"), inputs
    if report.unplaced:
        # جدولٌ ناقصٌ لا يصلح مسودّةً: يُرفض بالاسم قبل المُقيِّم ويبقى العددُ في اللقطة ليقرّر المالك.
        message = f"جدولٌ ناقص: {report.unplaced} حصّةً متعذّرة الوضع (طبقة المتعذّرات) — لا يُحفظ مسودّة"
        return RunResult(False, report, None, message, "rejected"), inputs
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
    from operations.scheduling_inputs import bell_lookup

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
        "lexicographic": result.report.lexicographic_dict(),
        "verdict": result.report.verdict,
        "evaluation": result.evaluation.as_dict(),
        # تخفيفاتُ المالك المعلَنة تُحفظ مع المسودّة (لا تخفيفَ صامت): HC5 للمُقيِّم، والباقي خياراتُ النموذج.
        "relaxations": {"hc5_run_caps": result.report.relaxations},
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
        snapshot["lexicographic"] = result.report.lexicographic_dict()
        snapshot["verdict"] = result.report.verdict
    if result.evaluation is not None:
        snapshot["evaluation"] = result.evaluation.as_dict()
    ScheduleGeneration.objects.filter(pk=generation.pk, status="running").update(
        status="failed",
        error_message=result.message[:2000],
        config_snapshot=snapshot,
        finished_at=timezone.now(),
    )


def _final_state(result: RunResult, stopped: bool) -> str:
    if result.reason in ("infeasible", "rejected"):
        return result.reason
    if result.ok and result.report:
        if result.report.status == "OPTIMAL":
            return "optimal"
        return "stopped" if stopped else "timeout"
    return "timeout" if result.reason == "timeout" else "failed"


def run_generation(generation: Any, config: SolverConfig, **kwargs: Any) -> RunResult:
    """يشغّل توليداً قائماً (صفٌّ `running`) ويكتب مصيرَه: مسودّةٌ مقبولة أو فشلٌ مفسَّر، مع سجلّ تقدّم."""
    from .progress import ProgressTracker

    started = time.monotonic()
    inputs = None
    tracker = kwargs.pop("progress", None) or ProgressTracker(generation.pk, config.max_seconds)
    try:
        result, inputs = run(
            generation.school, generation.academic_year, config, progress=tracker, **kwargs
        )
    except SchoolBusyError as error:
        result = RunResult(False, None, None, str(error), "busy")
    except ContractMissingError as error:
        result = RunResult(False, None, None, str(error), "no_model")
    if not result.ok:
        fail_generation(generation, result)
        tracker.finish(_final_state(result, tracker.stop_flag))
        return result
    persist_draft(generation, result, inputs, int((time.monotonic() - started) * 1000))
    tracker.finish(_final_state(result, tracker.stop_flag))
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

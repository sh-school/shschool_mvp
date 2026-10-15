"""تشخيصُ الاستحالة: أيُّ مجموعة قيودٍ صلبةٍ هي نواةُ التعارض (W-20261010-031، طوارئ D-346م).

«مستحيلٌ بالبرهان: القيودُ متعارضة» لا تقول أيَّ قيد. فهذا يبني النموذجَ نفسَه ثمّ يضع كلَّ ما أضافه
كلُّ كودٍ صلب (HC1…) خلف فرضيّةٍ (assumption)، فيعيد CP-SAT نواةً صغيرةً من الفرضيّات تكفي وحدَها
للاستحالة. التسميةُ تتمّ بتتبّع `_Ctx.count` دون تعديل ملفّ القيود الصلبة.

الحدّ الصادق: النواةُ كافيةٌ للاستحالة لا بالضرورة صغرى، وقيدٌ غيرُ مُعدَّدٍ (لم يمرّ بـ`count`) يبقى صلباً
دائماً فلا يظهر فيها. والتحقّقُ: تعطيلُ الأكواد المذكورة وحدَها يجب أن يُنهي الاستحالة أو يغيّر الحالة.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

from ortools.sat.python import cp_model

from . import hard_constraints
from .model import BuiltModel, ModelOptions, row_id  # noqa: F401  (row_id للمستدعين)


@dataclass
class Diagnosis:
    status: str
    core: list[str] = field(default_factory=list)
    seconds: float = 0.0
    codes: list[str] = field(default_factory=list)
    untagged: int = 0

    @property
    def message(self) -> str:
        if self.status != "INFEASIBLE":
            return f"الحالة {self.status} — لا نواةَ تعارض"
        if not self.core:
            return "مستحيلٌ بالبرهان — القيودُ المعدودة وحدَها لا تكفي لتفسيره"
        return "مستحيلٌ بالبرهان: التعارضُ بين " + "، ".join(self.core)


def _minimise(
    model, lits: dict[str, Any], core: list[str], *, max_seconds: float, workers: int
) -> list[str]:
    """يُسقط من النواة كلَّ كودٍ تبقى الاستحالةُ بدونه: ينتج نواةً صغرى محليّاً (لا أصغر عالميّة)."""
    kept = list(core)
    for code in list(core):
        trial = [c for c in kept if c != code]
        model.ClearAssumptions()
        for c in trial:
            model.AddAssumption(lits[c])
        solver = cp_model.CpSolver()
        solver.parameters.max_time_in_seconds = max_seconds
        solver.parameters.num_workers = workers
        if solver.StatusName(solver.Solve(model)) == "INFEASIBLE":
            kept = trial
    return sorted(kept)


def diagnose(
    inputs: Any, options: ModelOptions, *, max_seconds: float = 60.0, workers: int = 8
) -> Diagnosis:
    """نواةُ التعارض بالأكواد. لا يكتب شيئاً ولا يلمس قاعدة البيانات."""
    started = time.monotonic()
    lits: dict[str, Any] = {}
    state = {"cursor": 0, "model": None}
    original = hard_constraints._Ctx.count

    def tagging_count(self, code: str, n: int = 1) -> None:
        original(self, code, n)
        proto = self.m.Proto()
        total = len(proto.constraints)
        lit = lits.get(code)
        if lit is None:
            lit = lits[code] = self.m.NewBoolVar(f"assume_{code}")
            total = len(proto.constraints)
        for i in range(state["cursor"], total):
            ct = proto.constraints[i]
            if ct.has_no_overlap():
                continue
            ct.enforcement_literal.append(lit.Index())
        state["cursor"] = len(proto.constraints)

    hard_constraints._Ctx.count = tagging_count
    try:
        from .model import build_model

        built: BuiltModel = build_model(inputs, options)
    finally:
        hard_constraints._Ctx.count = original

    model = built.model
    proto = model.Proto()
    untagged = sum(
        1 for i in range(len(proto.constraints)) if not proto.constraints[i].enforcement_literal
    )
    for lit in lits.values():
        model.AddAssumption(lit)
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = max_seconds
    solver.parameters.num_workers = workers
    status = solver.StatusName(solver.Solve(model))
    core: list[str] = []
    if status == "INFEASIBLE":
        index_to_code = {lit.Index(): code for code, lit in lits.items()}
        core = sorted(
            {
                index_to_code[i]
                for i in solver.SufficientAssumptionsForInfeasibility()
                if i in index_to_code
            }
        )
    if core:
        core = _minimise(model, lits, core, max_seconds=max_seconds, workers=workers)
    return Diagnosis(
        status=status,
        core=core,
        seconds=round(time.monotonic() - started, 1),
        codes=sorted(lits),
        untagged=untagged,
    )

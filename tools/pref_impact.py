"""pref_impact.py — قياسُ أثر تفضيلات المعلّمين على توليد V2 قبل فتحها لهم (W-20261011-008).

قياسٌ لا تعديل: لا يغيّر المحرّكَ، ولا يكتب إلّا في قاعدة جلسةٍ معزولة (اسمُها يبدأ بـ`ss_` ومضيفُها
محلّيّ)، وكلُّ سيناريو داخل معاملةٍ يُتراجع عنها بعد قياسه — فتعود القاعدةُ كما كانت ولو انقطع التشغيل.

السيناريو حقلٌ واحدٌ من حقول شاشة المعلّم بقيمةٍ واحدة على نسبةٍ من المعلّمين، يُختارون بالأثقل نصاباً
أوّلاً (أسوأ حالة). ولا يُكتب التفضيلُ إلّا لمن تقبله الشاشةُ نفسُها (فحصُ السعة الفرديّ في
`views_schedule.teacher_preferences`)، فالسؤالُ المُجاب: ما تقبله الشاشةُ معلّماً معلّماً، ماذا يفعل
بالتوليد كلِّه؟

والتوليدُ مسارُ الزرّ بلا كتابة مسودّة: بوّابةُ الجدوى (`schedule_feasibility.check`) ثمّ `runner.run`
بسياسة المدرسة وسقوف الأولى والمُقيِّم المستقلّ وتشخيص الاستحالة. والمضافُ الوحيد غلافٌ على
`runner._run_stage` في هذه العمليّة وحدها يسجّل زمنَ كلّ مرحلةٍ وأوّلَ حلولها، ولا يمسّ البحث؛ ويقصّ
طبقةَ الجودة وحدَها إن طُلب (`--quality-seconds`) — فطبقةُ المخالفات بحصّتها وقطعِها كما في الزرّ (D-392م).

لا أسماءَ في المخرجات (PDPPL): المعلّمُ بمعرّفه المختصر ونصابه.

الاستعمال داخل حاوية الجلسة (سطرُ JSON لكلّ سيناريو يُلحق بالملفّ فور انتهائه):
    python tools/pref_impact.py --scenarios base,daily:4:100,gap:1:30 --quality-seconds 300 \
        --out tmp_reports/w008_pref_impact/runs.jsonl
"""

from __future__ import annotations

import argparse
import json
import math
import os
import sys
import threading
import time
from collections import defaultdict
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]

#: حقولُ شاشة المعلّم الثلاثة بأسمائها في `TeacherPreference`.
FIELDS = {"daily": "max_daily_periods", "gap": "max_gap", "consecutive": "max_consecutive"}
#: نطاقُ السيناريو الاختياريّ: يحصر المعلّمين بعدد نطاقات الجرس في إسناداتهم.
SCOPES = {"single": "نطاقُ جرسٍ واحد", "multi": "أكثرُ من نطاق جرس"}
#: ما يضعه `get_or_create` في الشاشة لصفٍّ جديد — فسيناريو الحقل الواحد يحمل الباقي كما يحفظه المعلّم.
SCREEN_DEFAULTS: dict[str, int | None] = {
    "max_daily_periods": 5,
    "max_consecutive": None,
    "max_gap": None,
}
WEEK_DAYS = 5
#: مضيفو قاعدة الجلسة المقبولون: الحاويةُ تصل القاعدةَ المشتركة عبر منفذ المضيف.
LOCAL_HOSTS = frozenset({"", "localhost", "127.0.0.1", "host.docker.internal", "db"})
DEFAULT_YEAR = "2026-2027"


# ───────────────────────── السيناريو والاختيار ─────────────────────────


@dataclass(frozen=True)
class Scenario:
    """حقلٌ وقيمةٌ ونسبةُ معلّمين (%)، ونطاقٌ اختياريّ يحصر المعلّمين بعدد نطاقات جرسهم. الأساسُ بلا حقل."""

    field: str = ""
    value: int | None = None
    share: int = 0
    scope: str = ""

    @property
    def key(self) -> str:
        if not self.field:
            return "base"
        return f"{self.field}:{self.value}:{self.share}" + (f":{self.scope}" if self.scope else "")

    @property
    def column(self) -> str:
        return FIELDS[self.field]

    @classmethod
    def parse(cls, spec: str) -> Scenario:
        spec = spec.strip()
        if spec == "base":
            return cls()
        parts = spec.split(":")
        if len(parts) not in (3, 4) or parts[0] not in FIELDS:
            raise ValueError(
                f"سيناريو غيرُ مفهوم: {spec!r} — الشكل daily|gap|consecutive:قيمة:نسبة[:single|multi]"
            )
        scope = parts[3] if len(parts) == 4 else ""
        if scope and scope not in SCOPES:
            raise ValueError(f"نطاقٌ غيرُ مفهوم: {scope!r} — single أو multi")
        value, share = int(parts[1]), int(parts[2])
        if not 0 < share <= 100 or value < 0:
            raise ValueError(f"سيناريو خارج المدى: {spec!r} — النسبة 1..100 والقيمة ≥ 0")
        return cls(parts[0], value, share, scope)


def scope_pool(loads: Mapping[str, int], bands: Mapping[str, int], scope: str) -> dict[str, int]:
    """المعلّمون الذين يُختار منهم: الكلّ، أو أصحابُ نطاق جرسٍ واحد (`single`)، أو أكثر من نطاق (`multi`)."""
    if not scope:
        return dict(loads)
    multi = scope == "multi"
    return {t: load for t, load in loads.items() if (bands.get(t, 1) > 1) is multi}


def select_teachers(loads: Mapping[str, int], share: int) -> list[str]:
    """الأثقلُ نصاباً أوّلاً ثمّ المعرّف (حتميّ)، بعددِ ⌈النسبة × الكلّ⌉."""
    if share <= 0 or not loads:
        return []
    count = math.ceil(len(loads) * share / 100)
    return sorted(loads, key=lambda t: (-loads[t], t))[:count]


def screen_slack(load: int, values: Mapping[str, Any], free_day: int | None) -> int | None:
    """فحصُ الشاشة كما في `teacher_preferences`: سعةُ الأسبوع ناقصَ النصاب، أو None إن ردّت الشاشةُ القيمة.

    تردّ الشاشةُ سقفاً يوميّاً دون حصّة القسمة (⌈النصاب ÷ الأيّام المفتوحة⌉)، ثمّ سعةً أسبوعيّةً دون النصاب.
    """
    from operations.preference_capacity import weekly_capacity

    days = WEEK_DAYS - (1 if free_day is not None else 0)
    needed = -(-load // days) if load else 0
    if values["max_daily_periods"] < needed:
        return None
    capacity = weekly_capacity(
        values["max_daily_periods"], values["max_consecutive"], values["max_gap"], free_day
    )
    return capacity - load if capacity >= load else None


def short(identifier: object) -> str:
    return str(identifier)[:8]


# ───────────────────────── الحارس ─────────────────────────


def isolation_problem(name: str, host: str, settings_module: str) -> str:
    """سببُ رفض التشغيل، أو فارغٌ إن كانت القاعدةُ قاعدةَ جلسةٍ محلّيّة."""
    if "production" in settings_module:
        return f"إعداداتُ الإنتاج ({settings_module})"
    if not name.startswith("ss_"):
        return f"القاعدة {name!r} ليست قاعدةَ جلسةٍ معزولة (ss_…)"
    if host not in LOCAL_HOSTS:
        return f"مضيفُ القاعدة {host!r} ليس محلّيّاً"
    return ""


def guard_database() -> str:
    from django.db import connection

    name = str(connection.settings_dict.get("NAME") or "")
    host = str(connection.settings_dict.get("HOST") or "")
    problem = isolation_problem(name, host, os.environ.get("DJANGO_SETTINGS_MODULE", ""))
    if problem:
        raise SystemExit(f"رُفض التشغيل: {problem}")
    return name


# ───────────────────────── الكتابة في القاعدة المعزولة ─────────────────────────


def screen_loads(school: Any, year: str) -> dict[str, int]:
    """نصابُ كلّ معلّمٍ كما تحسبه الشاشة: مجموعُ `weekly_periods` لإسناداته النشطة."""
    from django.db.models import Sum

    from operations.models import SubjectClassAssignment

    rows = (
        SubjectClassAssignment.objects.filter(
            school=school, academic_year=year, is_active=True, teacher__isnull=False
        )
        .values("teacher_id")
        .annotate(total=Sum("weekly_periods"))
    )
    return {str(r["teacher_id"]): int(r["total"] or 0) for r in rows}


def teacher_bands(school: Any, year: str) -> dict[str, int]:
    """عددُ نطاقات الجرس المختلفة في مهامّ كلّ معلّم، من مهامّ المولّد نفسِها (`build_tasks`)."""
    from operations.scheduling_inputs import build_tasks

    found: dict[str, set[str]] = defaultdict(set)
    for task in build_tasks(school, year):
        for member in task.members:
            found[str(member.teacher_id)].add(task.band_id or "")
    return {teacher: len(bands) for teacher, bands in found.items()}


def apply_scenario(
    school: Any,
    year: str,
    scenario: Scenario,
    loads: Mapping[str, int],
    bands: Mapping[str, int] | None = None,
) -> dict[str, Any]:
    """يكتب التفضيلَ لمن تقبله الشاشةُ من المختارين ويُرجع من كُتب له ومن رُدّ وأضيقَهم هامشاً."""
    from operations.models import TeacherPreference

    bands = bands or {}
    pool = scope_pool(loads, bands, scenario.scope)
    chosen = select_teachers(pool, scenario.share) if scenario.field else []
    existing = {
        str(p.teacher_id): p
        for p in TeacherPreference.objects.filter(
            school=school, academic_year=year, teacher_id__in=chosen
        )
    }
    applied: dict[str, int] = {}
    refused: list[str] = []
    for teacher in chosen:
        pref = existing.get(teacher)
        values = {name: getattr(pref, name) if pref else d for name, d in SCREEN_DEFAULTS.items()}
        values[scenario.column] = scenario.value
        slack = screen_slack(loads[teacher], values, pref.free_day if pref else None)
        if slack is None:
            refused.append(teacher)
            continue
        TeacherPreference.objects.update_or_create(
            teacher_id=teacher, school=school, academic_year=year, defaults=values
        )
        applied[teacher] = slack
    tight = min(applied, key=lambda t: (applied[t], -loads[t], t)) if applied else None
    return {
        "pool": len(pool),
        "selected": len(chosen),
        "applied": len(applied),
        "applied_multi_band": sum(1 for t in applied if bands.get(t, 1) > 1),
        "refused": len(refused),
        "applied_ids": sorted(applied),
        "tightest": None
        if tight is None
        else {"teacher": short(tight), "load": loads[tight], "slack": applied[tight]},
    }


# ───────────────────────── تسجيلُ المراحل ─────────────────────────


class Recorder:
    """بديلُ `ProgressTracker` في الذاكرة: لا يكتب في القاعدة ولا يطلب إيقافاً، ويسجّل كلَّ مرحلةٍ وحلولها."""

    def __init__(self) -> None:
        self.started = time.monotonic()
        self.stop_flag = False
        self.stages: list[dict[str, Any]] = []
        self._lock = threading.Lock()

    def _now(self) -> float:
        return round(time.monotonic() - self.started, 1)

    def begin(self, limit: float, grace: float | None = None) -> None:
        with self._lock:
            self.stages.append(
                {
                    "limit_s": round(limit, 1),
                    "grace_s": grace,
                    "start_s": self._now(),
                    "first_s": None,
                    "solutions": 0,
                }
            )

    def end(self, status: str, seconds: float) -> None:
        with self._lock:
            self.stages[-1].update(status=status, seconds=round(seconds, 1), done=True)

    def on_solution(self, objective: float, bound: float) -> None:
        with self._lock:
            stage = self.stages[-1] if self.stages else None
            if stage is None or stage.get("done"):
                return  # النداءُ الختاميّ من `solve()` بعد آخر مرحلة: ليس حلّاً جديداً
            stage["solutions"] += 1
            if stage["first_s"] is None:
                stage["first_s"] = round(self._now() - stage["start_s"], 1)
            stage["best"], stage["bound"] = objective, bound

    def on_bound(self, bound: float) -> None:
        return None

    def publish(self) -> bool:
        return False


def instrument(recorder: Recorder, quality_seconds: float | None = None) -> Any:
    """يلفّ `runner._run_stage` في هذه العمليّة: نداءُ الحلول في كلّ مرحلةٍ لا في الأخيرة وحدها، وتسجيلُ الحالة.

    و`quality_seconds` يقصّ الطبقةَ الأخيرة (الجودة) وحدَها؛ طبقةُ المخالفات تبقى بحصّتها وقطعِها كما في الزرّ،
    فالانكسارُ (لا حلَّ في حصّتها أو INFEASIBLE) يُقاس كما هو، ويُقارَن التخفيفُ بخطّ أساسٍ قيس بالقصّ نفسه.
    """
    from ortools.sat.python import cp_model

    from operations.scheduler_v2 import runner

    original = runner._run_stage

    def wrapped(
        built: Any,
        config: Any,
        progress: Any,
        max_seconds: float,
        _report: bool,
        stop_after_first: float | None = None,
    ) -> Any:
        # قطعُ طبقة المخالفات بعد أوّل حلّها (D-392م) يمرّ كما هو: القياسُ على سلوك الزرّ نفسِه.
        if _report and quality_seconds is not None:
            max_seconds = min(max_seconds, quality_seconds)
        recorder.begin(max_seconds, stop_after_first)
        solver, code, seconds = original(
            built, config, progress, max_seconds, True, stop_after_first
        )
        recorder.end(runner._status_name(cp_model, code), seconds)
        return solver, code, seconds

    runner._run_stage = wrapped
    return original


# ───────────────────────── تفاصيلُ المخالفات الصلبة ─────────────────────────


class BreachCapture:
    """يلتقط نداءات `grid_breaches` في آخر `evaluate_slots`: الأوّلُ صارمٌ والأخيرُ بعد التخفيف.

    المُقيِّمُ لا يُبقي إلّا العدّ (`hard_breaches`)، والتفصيلُ يلزم لمعرفة أين يختلف حكمُه عن الحلّال.
    """

    def __init__(self) -> None:
        self.calls: list[list[Any]] = []

    def install(self) -> Callable[[], None]:
        from operations import schedule_evaluator
        from operations.scheduler_v2 import runner

        grid_breaches, evaluate = schedule_evaluator.grid_breaches, runner.evaluate_slots

        def counted(*args: Any, **kwargs: Any) -> list[Any]:
            found = list(grid_breaches(*args, **kwargs))
            self.calls.append(found)
            return found

        def fresh(*args: Any, **kwargs: Any) -> Any:
            self.calls = []  # آخرُ تقييمٍ وحدَه
            return evaluate(*args, **kwargs)

        schedule_evaluator.grid_breaches, runner.evaluate_slots = counted, fresh

        def restore() -> None:
            schedule_evaluator.grid_breaches, runner.evaluate_slots = grid_breaches, evaluate

        return restore


def kept_breaches(calls: list[list[Any]]) -> list[Any]:
    """ما يبقى مخالفةً صلبة كما في `evaluate_slots`: الصارمةُ التي لم يرفعها التخفيف."""
    if not calls:
        return []
    if len(calls) == 1:
        return list(calls[0])
    relaxed = {b.key for b in calls[-1]}
    return [b for b in calls[0] if b.key in relaxed]


def _short_key(part: Any) -> Any:
    if isinstance(part, tuple):
        return [_short_key(p) for p in part]
    return short(part) if isinstance(part, str) and len(part) > 8 else part


def breach_details(
    breaches: Iterable[Any],
    slots: Iterable[tuple[Any, ...]],
    class_band: Mapping[str, str],
    loads: Mapping[str, int] | None = None,
) -> list[dict[str, Any]]:
    """الرمزُ واليومُ والحصّةُ ومفتاحُ المخالفة بمعرّفاتٍ مختصرة، وحصصُ المعلّم يومَها (رقمٌ ونطاق) — بلا أسماء."""
    cells: dict[tuple[str, int], set[tuple[int, str]]] = defaultdict(set)
    for cls, _subject, teacher, day, period in slots:
        cells[str(teacher), day].add((period, short(class_band.get(cls, "") or "-")))
    out = []
    for breach in list(breaches)[:20]:
        item: dict[str, Any] = {
            "code": breach.code,
            "day": breach.day,
            "period": breach.period,
            "key": _short_key(tuple(breach.key[1:])),
        }
        teachers = breach.key[1] if len(breach.key) > 1 and isinstance(breach.key[1], tuple) else ()
        if teachers:
            item["cells"] = {
                short(t): [list(c) for c in sorted(cells.get((str(t), breach.day), ()))]
                for t in teachers
            }
            item["loads"] = {short(t): (loads or {}).get(str(t)) for t in teachers}
        out.append(item)
    return out


# ───────────────────────── الخلاصة ─────────────────────────


def _interval(inputs: Any, cls: str, day: int, period: int) -> tuple[int, int]:
    key = f"{inputs.class_band.get(cls, '')}|{'thursday' if day == 4 else 'regular'}"
    found = inputs.times.get(key, {}).get(period)
    return tuple(found) if found else (period * 1000, period * 1000 + 1)  # type: ignore[return-value]


def teacher_stress(
    slots: Iterable[tuple[str, str, str, int, int]],
    interval: Any,
    joinable_gap: int,
) -> dict[str, dict[str, int]]:
    """لكلّ معلّم: أزواجُ التلاصق (فجوةٌ ≤ الحدّ بالدقائق)، والفراغاتُ بين أوّل حصّةٍ وآخرِها، وأثقلُ يوم.

    `interval(cls, day, period)` ← (بداية، نهاية) بالدقائق. الحصّةُ المنقسمة (خانةٌ لشعبتين) تُعدّ مرّةً واحدة.
    """
    days: dict[tuple[str, int], set[tuple[int, int, int]]] = defaultdict(set)
    for cls, _subj, teacher, day, period in slots:
        start, end = interval(cls, day, period)
        days[(teacher, day)].add((start, end, period))
    out: dict[str, dict[str, int]] = defaultdict(lambda: {"touch": 0, "gaps": 0, "max_day": 0})
    for (teacher, _day), cells in days.items():
        ordered = sorted(cells)
        periods = sorted({p for _s, _e, p in ordered})
        row = out[teacher]
        row["touch"] += sum(
            1
            for a, b in zip(ordered, ordered[1:], strict=False)
            if 0 <= b[0] - a[1] <= joinable_gap
        )
        row["gaps"] += periods[-1] - periods[0] + 1 - len(periods)
        row["max_day"] = max(row["max_day"], len(periods))
    return dict(out)


def stress_summary(
    stress: Mapping[str, Mapping[str, int]], focus: Iterable[str], loads: Mapping[str, int]
) -> dict[str, Any]:
    """المجاميعُ، والأكثرُ تضرّراً (تلاصقٌ + فراغات) بين أصحاب التفضيل — أو بين الكلّ في الأساس."""
    pool = [t for t in focus if t in stress] or list(stress)
    totals = {
        "touch": sum(s["touch"] for s in stress.values()),
        "gaps": sum(s["gaps"] for s in stress.values()),
        "max_day": max((s["max_day"] for s in stress.values()), default=0),
    }
    if not pool:
        return {"totals": totals, "worst": None}
    worst = max(pool, key=lambda t: (stress[t]["touch"] + stress[t]["gaps"], loads.get(t, 0), t))
    return {
        "totals": totals,
        "worst": {"teacher": short(worst), "load": loads.get(worst, 0), **stress[worst]},
    }


def gate_summary(report: Any) -> dict[str, Any]:
    """حكمُ بوّابة ما قبل التوليد بالرموز والعدد — لا أسماء (صفوفُ العجز تحمل الاسم فلا تُنقل)."""
    return {
        "blocked": bool(report.blocking),
        "codes": [f.code for f in report.blocking],
        "warnings": [f.code for f in report.warnings],
        "min_unplaceable": report.minimum_unplaceable,
    }


def _masked_diagnosis(diagnosis: Any) -> dict[str, Any]:
    data = diagnosis.as_dict()
    data["teachers"] = [short(t) for t in data["teachers"]]
    data["loads"] = {short(t): n for t, n in data["loads"].items()}
    return data


def result_summary(result: Any) -> dict[str, Any]:
    out: dict[str, Any] = {
        "ok": result.ok,
        "reason": result.reason,
        "message": result.message[:500],
    }
    report, evaluation = result.report, result.evaluation
    if report is not None:
        out.update(
            status=report.status,
            solver_s=round(report.seconds, 1),
            layers=dict(report.layers),
            hc5_relaxed_teachers=len(report.relaxations),
            hc22_override_teachers=len(report.first_caps),
        )
    if evaluation is not None:
        out.update(
            accepted=evaluation.accepted,
            eased=dict(evaluation.eased),
            hard=dict(evaluation.hard_breaches),
            soft=dict(evaluation.soft_counts),
            quality=evaluation.objective_value,
            unplaced=evaluation.infeasibility_value,
        )
    if result.diagnosis is not None:
        out["diagnosis"] = _masked_diagnosis(result.diagnosis)
    return out


# ───────────────────────── التشغيل ─────────────────────────


def measure(
    school: Any,
    year: str,
    scenario: Scenario,
    config: Any,
    loads: Mapping[str, int],
    quality_seconds: float | None = None,
    bands: Mapping[str, int] | None = None,
) -> dict[str, Any]:
    """سيناريو واحد داخل معاملةٍ يُتراجع عنها: كتابةُ التفضيل، البوّابة، التوليد، الخلاصة."""
    from django.db import transaction

    from operations import schedule_feasibility
    from operations.scheduler_v2 import runner
    from operations.scheduler_v2.soft_constraints import JOINABLE_GAP_MINUTES

    row: dict[str, Any] = {
        "scenario": scenario.key,
        "field": scenario.field,
        "scope": scenario.scope,
    }
    row.update(value=scenario.value, share=scenario.share)
    recorder = Recorder()
    capture = BreachCapture()
    original = instrument(recorder, quality_seconds)
    restore = capture.install()
    try:
        with transaction.atomic():
            applied = apply_scenario(school, year, scenario, loads, bands)
            focus = applied.pop("applied_ids")
            row.update(applied)
            row["gate"] = gate_summary(schedule_feasibility.check(school, year))
            started = time.monotonic()
            result, inputs = runner.run(school, year, config, progress=recorder)
            row["wall_s"] = round(time.monotonic() - started, 1)
            row.update(result_summary(result))
            if result.report is not None and result.report.slots:
                stress = teacher_stress(
                    result.report.slots,
                    lambda c, d, p: _interval(inputs, c, d, p),
                    JOINABLE_GAP_MINUTES,
                )
                row["stress"] = stress_summary(stress, focus, loads)
                if row.get("hard"):
                    row["breaches"] = breach_details(
                        kept_breaches(capture.calls),
                        result.report.slots,
                        inputs.class_band,
                        loads,
                    )
            transaction.set_rollback(True)
    finally:
        runner._run_stage = original
        restore()
    row["stages"] = recorder.stages
    return row


def setup_django() -> None:
    sys.path.insert(0, str(ROOT))
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "shschool.settings.development")
    import django

    django.setup()


def parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="قياسُ أثر تفضيلات المعلّمين على توليد V2")
    parser.add_argument("--scenarios", required=True, help="مثل base,daily:4:100,gap:1:30")
    parser.add_argument(
        "--seconds", type=float, default=1800.0, help="مهلةُ الحلّال (افتراضُ الزرّ 1800)"
    )
    parser.add_argument(
        "--quality-seconds",
        type=float,
        default=None,
        help="سقفُ طبقة الجودة وحدها؛ بلا قيمة = كالزرّ",
    )
    parser.add_argument("--workers", type=int, default=None)
    parser.add_argument("--seed", type=int, default=None)
    parser.add_argument("--year", default=DEFAULT_YEAR)
    parser.add_argument("--out", required=True, help="ملفُّ JSONL تُلحق به السطور")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    scenarios = [Scenario.parse(s) for s in args.scenarios.split(",") if s.strip()]
    setup_django()
    database = guard_database()
    from core.models import School
    from operations.scheduler_v2 import runner

    school = School.objects.get()
    loads = screen_loads(school, args.year)
    bands = teacher_bands(school, args.year)
    config = runner.SolverConfig(
        seed=runner.DEFAULT_SEED if args.seed is None else args.seed,
        workers=runner.DEFAULT_WORKERS if args.workers is None else args.workers,
        max_seconds=args.seconds,
    )
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    for scenario in scenarios:
        try:
            row = measure(school, args.year, scenario, config, loads, args.quality_seconds, bands)
        except Exception as error:  # noqa: BLE001 — سيناريو يسقط يُسجَّل ولا يوقف الدفعة
            row = {"scenario": scenario.key, "error": f"{type(error).__name__}: {error}"[:500]}
            row.update(field=scenario.field, value=scenario.value, share=scenario.share)
            row.update(scope=scenario.scope)
            row.update(selected=0, applied=0, gate={"codes": []})
        row.update(
            database=database,
            teachers=len(loads),
            seconds_cap=args.seconds,
            quality_cap=args.quality_seconds,
            seed=config.seed,
            workers=config.workers,
            finished_at=time.strftime("%Y-%m-%dT%H:%M:%S"),
            loadavg=[round(x, 1) for x in os.getloadavg()],
        )
        with out.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
        eased = row.get("eased", {})
        print(
            f"{scenario.key}: {row.get('status')} {row.get('reason')} {row.get('wall_s')}ث"
            f" HC5={eased.get('HC5', 0)} HC22={eased.get('HC22', 0)}"
            f" طُبّق={row['applied']}/{row['selected']} بوّابة={row['gate']['codes']}",
            flush=True,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

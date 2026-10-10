"""قياس منحنى الهدف مقابل الميزانية الزمنيّة لمولّد V2 على نسخة A1 المقنَّعة (W-20261009-029).

قياسٌ فقط: لا يمسّ المولّد ولا الإنتاج. يبني مسألةً من تصدير A1 المقنَّع (هويّاتٌ صناعيّةٌ T/C/S/R، بلا أسماء)
في قاعدة اختبارٍ مؤقّتة، ثمّ يحلّها بالنموذج والهدف والإعدادات الافتراضيّة نفسها التي يستعملها المشغّل
(`runner.default_builder` وبذرتُه وعمّاله)، مرّةً لكلّ ميزانية، ويسجّل لكلّ حلٍّ تحسينيّ (الزمن، الهدف، الحدّ).

التشغيل (داخل حاوية الويب؛ ملفُّ البيانات خارج المستودع عمداً — لا يُودَع):

    A1_RAW=/tmp/a1_raw_3.txt A1_OUT=/tmp/budget_curve.json BUDGETS=120,300,600,900 \\
    python -m pytest docs/schedule_v2/budget_curve_a1.py -q -p no:cacheprovider -s

متغيّرات اختياريّة: SEED (الافتراضيّ بذرة المشغّل)، WORKERS (الافتراضيّ عمّال المشغّل).
التخفيفاتُ المعلَنة كما في خطوة الإنتاج `c`: run_cap=2 وno_6_7 والثلاثيات بالرقم، وtouch_relaxed لكلّ المعلّمين.
(`first_cap_override` لاثني عشر معلّماً غيرُ مطبَّق: هويّاتُهم الحقيقيّة لا تُطابَق بالهويّات المقنَّعة.)
"""

from __future__ import annotations

import json
import os
import threading
import time
from collections import defaultdict
from datetime import time as clock_time
from pathlib import Path

import pytest

pytestmark = pytest.mark.django_db

FX = Path(__file__).resolve().parent / "fixture_anonymized.json"


def _clock(m: int) -> clock_time:
    return clock_time(m // 60, m % 60)


class _Recorder:
    """بديلُ ProgressTracker: يسجّل كلَّ حلٍّ وزمنَه ولا يكتب في القاعدة."""

    def __init__(self) -> None:
        self.t0 = time.monotonic()
        self.trace: list[tuple[float, float, float]] = []
        self._lock = threading.Lock()

    def on_solution(self, objective: float, bound: float) -> None:
        with self._lock:
            self.trace.append((round(time.monotonic() - self.t0, 2), objective, bound))

    def publish(self) -> bool:  # يستدعيه Ticker كلَّ ثانية
        return False


def _load_school(raw_path: Path):
    from core.models import ClassGroup, TimeBand
    from operations.models import (
        SchedulingResource,
        Subject,
        SubjectClassAssignment,
        TeacherExemption,
        TimeSlotConfig,
    )
    from tests.conftest import SchoolFactory, UserFactory

    raw = raw_path.read_text(encoding="utf-8")
    j, _ = json.JSONDecoder().raw_decode(raw[raw.find("A1JSON>>") + 8 :])
    fx = json.loads(FX.read_text(encoding="utf-8"))
    year = "2026-2027"
    school = SchoolFactory()

    bands = {}
    for key in fx["times"]:
        code = key.split("|")[0]
        if code not in bands:
            bands[code] = TimeBand.objects.create(school=school, code=code.lower(), name=code)
    for key, periods in fx["times"].items():
        code, day_type = key.split("|")
        for number, (a, b) in periods.items():
            TimeSlotConfig.objects.create(
                school=school,
                band=bands[code],
                day_type=day_type,
                period_number=int(number),
                start_time=_clock(a),
                end_time=_clock(b),
            )

    ped = {s["code"]: s["pedagogy"] for s in fx["subjects"]}
    subjects = {
        s["id"]: Subject.objects.create(
            school=school,
            name_ar=s["id"],
            code=s["code"],
            pedagogy=ped.get(s["code"], "regular"),
            requires_double_period=s["requires_double_period"],
        )
        for s in j["subjects"]
    }
    teachers: dict = {}
    classes: dict = {}
    cells = defaultdict(set)
    for p in j["published_slots"]:
        cells[p["class_group"]].add((p["day_of_week"], p["period_number"]))
    for a in (x for x in j["assignments"] if x["is_active"]):
        c = a["class_group"]
        if c not in classes:
            band = "B-03" if len({p for d, p in cells[c] if d == 4}) >= 7 else "B-01"
            sec = len(fx["bell"][f"{band}|thursday"]["periods"]) >= 7
            classes[c] = ClassGroup.objects.create(
                school=school,
                grade="G10" if sec else "G7",
                section=c,
                level_type="sec" if sec else "prep",
                time_band=bands[band],
                academic_year=year,
            )
        if a["teacher"] not in teachers:
            teachers[a["teacher"]] = UserFactory(full_name=a["teacher"])
        SubjectClassAssignment.objects.create(
            school=school,
            class_group=classes[c],
            subject=subjects[a["subject"]],
            teacher=teachers[a["teacher"]],
            weekly_periods=a["weekly_periods"],
            academic_year=year,
            parallel_group=(a["parallel_group"] or "").strip(),
        )
    for e in j["exemptions"]:
        if not e["is_active"] or e["teacher"] not in teachers:
            continue
        TeacherExemption.objects.create(
            school=school,
            academic_year=year,
            teacher=teachers[e["teacher"]],
            exemption_type=e["exemption_type"],
            day_of_week=e["day_of_week"],
            period_number=e["period_number"],
            reason="A1",
            source=e["source"],
        )
    sc = {s["code"]: s["id"] for s in j["subjects"]}
    res_sub = {"R001": ["PE"], "R002": ["ART"], "R003": ["TECH", "CS", "IT"]}
    for r in j["resources"]:
        res = SchedulingResource.objects.create(school=school, name=r["id"], capacity=r["capacity"])
        res.subjects.set([subjects[sc[c]] for c in res_sub.get(r["id"], []) if c in sc])
    return school, year, teachers


@pytest.mark.skipif(not os.environ.get("A1_RAW"), reason="لا بيانات A1 (A1_RAW)")
def test_budget_curve(capsys):
    from ortools.sat.python import cp_model  # noqa: F401 — فشلٌ مبكّر إن غابت

    from operations.scheduler_v2 import runner

    school, year, teachers = _load_school(Path(os.environ["A1_RAW"]))
    budgets = [int(x) for x in os.environ.get("BUDGETS", "120,300,600,900").split(",")]
    seed = int(os.environ.get("SEED", runner.DEFAULT_SEED))
    workers = int(os.environ.get("WORKERS", runner.DEFAULT_WORKERS))
    spec = {
        "run_cap": 2,
        "no_6_7": True,
        "triples_by_number": True,
        "touch_relaxed": sorted(str(t.pk) for t in teachers.values()),
    }
    inputs = runner.load_inputs(school, year)
    results = []
    for budget in budgets:
        t_build = time.monotonic()
        options = runner.default_options(inputs, runner.options_from_relaxations(dict(spec)))
        built = runner.default_builder()(inputs, options)
        add_objective = runner.default_objective()
        if add_objective is not None:
            add_objective(built, inputs)
        build_s = round(time.monotonic() - t_build, 2)

        rec = _Recorder()
        config = runner.SolverConfig(seed=seed, workers=workers, max_seconds=budget)
        report = runner.solve(built, config, rec)
        hard = None
        if report.slots:
            report.relaxations = {
                r["teacher"]: int(str(r["relaxed"]).rsplit("_", 1)[-1])
                for r in getattr(built, "relaxations", [])
                if r.get("code") == "HC5"
            }
            ev = runner.evaluate_report(school, year, report)
            hard = ev.hard_breaches
        row = {
            "budget_s": budget,
            "seed": seed,
            "workers": workers,
            "build_s": build_s,
            "status": report.status,
            "wall_s": round(report.seconds, 1),
            "objective": report.objective,
            "first_solution_s": rec.trace[0][0] if rec.trace else None,
            "first_objective": rec.trace[0][1] if rec.trace else None,
            "solutions": len(rec.trace),
            "slots": len(report.slots),
            "hard_breaches": hard,
            "trace": rec.trace,
        }
        results.append(row)
        with capsys.disabled():
            print(
                "[BUDGET]",
                json.dumps({k: v for k, v in row.items() if k != "trace"}, default=str),
                flush=True,
            )
        out = os.environ.get("A1_OUT")
        if out:
            Path(out).write_text(
                json.dumps(results, ensure_ascii=False, default=str), encoding="utf-8"
            )

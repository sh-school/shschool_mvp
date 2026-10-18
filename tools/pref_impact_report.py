"""pref_impact_report.py — تقريرُ المالك العربيّ (HTML) من سطور `pref_impact.py` (W-20261011-008).

يقرأ ملفّ JSONL ويكتب صفحةً مستقلّةً بلا موارد خارجيّة: العتبةُ لكلّ حقل، وجدولُ السيناريوهات بلا خانةٍ فارغة،
ومعنى كلّ رمزٍ ورقم. والحكمُ على السيناريو آليٌّ من السطر نفسه بقواعدَ معلنةٍ في الصفحة (`verdict`)، فلا
تُكتب عتبةٌ بالتقدير.

    python tools/pref_impact_report.py tmp_reports/w008_pref_impact/runs.jsonl \
        --out tmp_reports/w008_pref_impact/report.html
"""

from __future__ import annotations

import argparse
import html
import json
import math
import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

#: أسماءُ الحقول كما في شاشة المعلّم.
FIELD_TITLES = {
    "daily": "أقصى عدد حصص يومية",
    "gap": "أقصى فجوة بين حصتين",
    "consecutive": "أقصى حصص متتالية",
}
#: ما يحكم به المحرّكُ على كلّ حقل.
FIELD_CODES = {"daily": "DAILY_CAP/HC16", "gap": "HC10", "consecutive": "HC5 (المُقيِّم وحده)"}
#: نطاقُ السيناريو كما في `pref_impact.SCOPES` (منسوخٌ لأنّ التقرير يُشغَّل سكربتاً مستقلّاً).
SCOPE_TITLES = {"single": "معلّمو نطاق جرسٍ واحد", "multi": "معلّمون في أكثر من نطاق جرس"}
#: الأحكامُ التي تُعدّ انكساراً: التوليدُ لا يُخرج مسودّةً مقبولةً أو يُخرجها بجدولٍ أضيقَ من الأساس.
BREAKS = frozenset({"gate", "infeasible", "timeout", "rejected", "failed", "hc", "error"})
VERDICT_TITLES = {
    "ok": "سليم",
    "hc": "زيادةٌ في التخفيف",
    "gate": "رفضته البوّابة",
    "infeasible": "مستحيلٌ بالبرهان",
    "timeout": "انقضت المهلة بلا حلّ",
    "rejected": "رفضه المُقيِّم",
    "failed": "فشل",
    "error": "خطأ تشغيل",
}
STATUS_TITLES = {
    "OPTIMAL": "أمثلُ بالبرهان",
    "FEASIBLE": "حلٌّ مقبولٌ غيرُ مثبَت الأمثليّة",
    "INFEASIBLE": "مستحيلٌ بالبرهان",
    "UNKNOWN": "لا حلَّ في المهلة",
}


# ───────────────────────── الحكم والعتبة ─────────────────────────


@dataclass(frozen=True)
class Baseline:
    """الأساسُ بلا تفضيلاتٍ جديدة، وعرضُ تذبذبه بين تكراراته."""

    hc5: int
    hc22: int
    band5: int
    band22: int
    runs: int

    @classmethod
    def of(cls, rows: Iterable[Mapping[str, Any]]) -> Baseline:
        base = [r for r in rows if r.get("scenario") == "base" and r.get("ok")]
        if not base:
            raise ValueError("لا تشغيلَ أساسٍ ناجحٍ في الملفّ — لا يُحكم على سيناريو بلا أساس")
        hc5 = [int(r.get("eased", {}).get("HC5", 0)) for r in base]
        hc22 = [int(r.get("eased", {}).get("HC22", 0)) for r in base]
        # نطاقُ التذبذب: فرقُ التكرارات، ولا يقلّ عن 5% من HC5 ولا عن معلّمٍ واحدٍ في HC22.
        band5 = max(max(hc5) - min(hc5), math.ceil(0.05 * max(hc5)), 1)
        band22 = max(max(hc22) - min(hc22), 1)
        return cls(max(hc5), max(hc22), band5, band22, len(base))


def verdict(row: Mapping[str, Any], base: Baseline) -> str:
    """حكمُ السيناريو بالترتيب الذي يراه المستخدم: البوّابةُ قبل الحلّال، والحلّالُ قبل المُقيِّم، ثمّ الأثر."""
    if row.get("error"):
        return "error"
    if row.get("gate", {}).get("blocked"):
        return "gate"
    if row.get("status") == "INFEASIBLE" or row.get("reason") == "infeasible":
        return "infeasible"
    reason = row.get("reason")
    if reason in ("timeout", "rejected"):
        return str(reason)
    if not row.get("ok"):
        return "failed"
    eased = row.get("eased", {})
    if int(eased.get("HC5", 0)) > base.hc5 + base.band5:
        return "hc"
    if int(eased.get("HC22", 0)) > base.hc22 + base.band22:
        return "hc"
    return "ok"


def threshold(rows: Iterable[Mapping[str, Any]], field: str, base: Baseline) -> dict[str, Any]:
    """على 100% من المعلّمين: آخرُ قيمةٍ سليمة وأوّلُ قيمةٍ تنكسر (من الأرخى إلى الأشدّ)، ثمّ أدنى نسبةٍ تكسرها."""
    # سيناريوهاتُ النطاق (`single`/`multi`) تفسّر الانكسار ولا تحدّد العتبة: العتبةُ لكلّ المعلّمين.
    mine = [r for r in rows if r.get("field") == field and not r.get("scope")]
    full = {r["value"]: r for r in mine if r.get("share") == 100}
    safe = broken = None
    for value in sorted(full, reverse=True):  # القيمةُ الأصغرُ أشدّ في الحقول الثلاثة
        if verdict(full[value], base) in BREAKS:
            broken = value
            break
        safe = value
    shares = sorted(r["share"] for r in mine if r["value"] == broken and verdict(r, base) in BREAKS)
    # سليمٌ لم يُطبَّق فيه التفضيلُ على أحد (رفضته الشاشةُ للجميع) ليس صموداً: هو الأساسُ نفسُه.
    held = sorted(
        r["share"]
        for r in mine
        if r["value"] == broken and verdict(r, base) not in BREAKS and r.get("applied", 1)
    )
    unapplied = sorted(
        r["share"]
        for r in mine
        if r["value"] == broken and verdict(r, base) not in BREAKS and not r.get("applied", 1)
    )
    return {
        "field": field,
        "safe": safe,
        "broken": broken,
        "broken_kind": None if broken is None else verdict(full[broken], base),
        "min_breaking_share": shares[0] if shares else None,
        "max_holding_share": held[-1] if held else None,
        "unapplied_shares": unapplied,
        "measured": sorted(full, reverse=True),
    }


def conflict(row: Mapping[str, Any], kind: str, base: Baseline) -> str:
    """القيدُ المتعارض أو الأعلى أثراً — لا يُترك فارغاً."""
    if kind == "error":
        return str(row.get("error", ""))[:120]
    if kind == "gate":
        return "بوّابة الجدوى: " + "، ".join(row["gate"]["codes"])
    if kind == "infeasible":
        return _diagnosis_text(row)
    field = row.get("field") or ""
    own = FIELD_CODES.get(field, "")
    if kind == "timeout":
        return f"{own} — لم يجد الحلّالُ جدولاً في المهلة"
    if kind == "rejected":
        hard = row.get("hard") or {}
        return "مخالفاتٌ صلبة: " + (_pairs(hard) or str(row.get("message", ""))[:120])
    return _impact_text(row, base, own)


def _diagnosis_text(row: Mapping[str, Any]) -> str:
    diag = row.get("diagnosis") or {}
    own = FIELD_CODES.get(str(row.get("field") or ""), "")
    if diag.get("codes"):
        return f"{own}؛ يزول بإيقاف: " + " + ".join(diag["codes"])
    if diag.get("switchable_cures"):
        return f"{own} مع أكثرَ من ثلاثةِ قيودٍ قابلةٍ للإيقاف"
    return f"{own} في النواة الصلبة (لا يزول بإيقاف أيّ قيدٍ قابلٍ للإيقاف)"


def _impact_text(row: Mapping[str, Any], base: Baseline, own: str) -> str:
    eased = row.get("eased", {})
    d5 = int(eased.get("HC5", 0)) - base.hc5
    d22 = int(eased.get("HC22", 0)) - base.hc22
    if d5 <= 0 and d22 <= 0:
        return f"لا زيادة على الأساس ({own})" if own else "الأساس"
    code = "HC5" if d5 >= d22 else "HC22"
    return f"{code} +{max(d5, d22)} على الأساس ({own})"


#: أيّامُ الدوام بترتيب المحرّك (0 = الأحد … 4 = الخميس).
def _periods(count: object) -> str:
    """العددُ مع تمييزه: من 3 إلى 10 «حصص»، وغيرُها «حصّة»."""
    return f"{count} حصص" if isinstance(count, int) and 3 <= count <= 10 else f"{count} حصّة"


DAY_NAMES = ("الأحد", "الاثنين", "الثلاثاء", "الأربعاء", "الخميس")


def _breach_text(breach: Mapping[str, Any]) -> str:
    """صاحبُ أوّل مخالفةٍ صلبة: معرّفُه ونصابُه ويومُه وحصصُه فيه برقمها ونطاق جرسها."""
    (teacher, cells), *_ = breach["cells"].items()
    load = (breach.get("loads") or {}).get(teacher, "؟")
    day = DAY_NAMES[breach["day"]] if 0 <= breach["day"] < len(DAY_NAMES) else breach["day"]
    periods = "، ".join(f"{p} ({band})" for p, band in cells)
    return f"{teacher} ({_periods(load)}) يوم {day}: الحصص {periods}"


def teacher_cell(row: Mapping[str, Any], kind: str) -> str:
    """المعلّمُ بمعرّفه المختصر ونصابه: من التشخيص عند الاستحالة، وصاحبُ المخالفة عند رفض المُقيِّم،
    وإلّا الأكثرُ تضرّراً أو الأضيقُ هامشاً."""
    diag = row.get("diagnosis") or {}
    breaches = [b for b in row.get("breaches") or [] if b.get("cells")]
    if kind == "rejected" and breaches:
        more = len(row["breaches"]) - 1
        return _breach_text(breaches[0]) + (f"، و{more} مخالفةً غيرُها" if more else "")
    if kind == "infeasible" and diag.get("teachers"):
        first = diag["teachers"][0]
        more = len(diag["teachers"]) - 1
        tail = f" و{more} غيرُه" if more else ""
        load = _periods(diag.get("loads", {}).get(first, "؟"))
        return f"{first} ({load}){tail} من {diag.get('teachers_total', '؟')}"
    worst = (row.get("stress") or {}).get("worst")
    if worst:
        return (
            f"{worst['teacher']} ({_periods(worst['load'])}): تلاصق {worst['touch']}،"
            f" فراغ {worst['gaps']}، أثقلُ يوم {worst['max_day']}"
        )
    tight = row.get("tightest")
    if tight:
        return f"{tight['teacher']} ({_periods(tight['load'])}) هامشُه {tight['slack']}"
    return "لا معلّمَ طُبّق عليه التفضيل" if row.get("field") else "—"


def _pairs(data: Mapping[str, Any]) -> str:
    return "، ".join(f"{k}={v}" for k, v in sorted(data.items()))


# ───────────────────────── الصفحة ─────────────────────────


def _e(value: object) -> str:
    return html.escape(str(value))


def _seconds(row: Mapping[str, Any]) -> str:
    stages = row.get("stages") or []
    first = next((s.get("first_s") for s in stages if s.get("first_s") is not None), None)
    total = row.get("wall_s", "—")
    return f"{total}ث" + (f" (أوّلُ حلٍّ {first}ث)" if first is not None else " (لا حلّ)")


def _eased(row: Mapping[str, Any], code: str) -> object:
    """صفرٌ لجدولٍ قُيّم بلا تخفيفٍ من هذا الرمز، وشَرطةٌ حين لا جدولَ يُقيَّم أصلاً."""
    return row["eased"].get(code, 0) if "eased" in row else "—"


def _totals(row: Mapping[str, Any]) -> str:
    """أزواجُ التلاصق والحصصُ الفارغة على كلّ المعلّمين: ما يبقى قابلاً للمقارنة حين يتغيّر سقفُ HC5 الشخصيّ."""
    totals = (row.get("stress") or {}).get("totals")
    return "—" if not totals else f"{totals['touch']} / {totals['gaps']}"


def scenario_rows(rows: list[Mapping[str, Any]], base: Baseline) -> str:
    out = []
    for row in rows:
        kind = verdict(row, base)
        title = FIELD_TITLES.get(str(row.get("field")), "الأساس — بلا تفضيلاتٍ جديدة")
        if row.get("scope"):
            title += f" — {SCOPE_TITLES[row['scope']]} فقط"
        value = "—" if not row.get("field") else row.get("value")
        out.append(
            "<tr class='v-{k}'><td>{s}</td><td>{t}</td><td class='n'>{v}</td><td class='n'>{sh}</td>"
            "<td class='n'>{ap}</td><td>{g}</td><td>{st}</td><td class='n'>{sec}</td>"
            "<td class='n'>{h5}</td><td class='n'>{h22}</td><td class='n'>{tot}</td>"
            "<td>{c}</td><td>{te}</td>"
            "<td><b>{vt}</b></td></tr>".format(
                k=_e(kind),
                s=_e(row.get("scenario")),
                t=_e(title),
                v=_e(value),
                sh=_e(f"{row.get('share') or 0}%" if row.get("field") else "—"),
                ap=_e(f"{row.get('applied', 0)}/{row.get('selected', 0)}"),
                g=_e(
                    "رفض: " + "، ".join(row["gate"]["codes"])
                    if row["gate"].get("blocked")
                    else "تمرّ"
                ),
                st=_e(STATUS_TITLES.get(str(row.get("status")), str(row.get("status") or "—"))),
                sec=_e(_seconds(row)),
                h5=_e(_eased(row, "HC5")),
                h22=_e(_eased(row, "HC22")),
                tot=_e(_totals(row)),
                c=_e(conflict(row, kind, base)),
                te=_e(teacher_cell(row, kind)),
                vt=_e(VERDICT_TITLES[kind]),
            )
        )
    return "\n".join(out)


def threshold_rows(rows: list[Mapping[str, Any]], base: Baseline) -> str:
    out = []
    for field in FIELD_TITLES:
        found = threshold(rows, field, base)
        if not found["measured"]:
            continue
        safe = "لا قيمةَ سليمة" if found["safe"] is None else found["safe"]
        if found["broken"] is None:
            broken = f"لا انكسارَ حتى أشدّ قيمةٍ مقيسة ({found['measured'][-1]})"
        else:
            broken = f"{found['broken']} — {VERDICT_TITLES[found['broken_kind']]}"
        share = found["min_breaking_share"]
        held = found["max_holding_share"]
        coverage = "—" if share is None else f"تنكسر من {share}%"
        if held is not None:
            coverage += f"، وتصمد عند {held}%"
        for unapplied in found["unapplied_shares"]:
            coverage += f"، وعند {unapplied}% رفضتها الشاشةُ لكلّ المختارين فلم تُطبَّق على أحد"
        out.append(
            f"<tr><td>{_e(FIELD_TITLES[field])}</td><td class='n'><b>{_e(safe)}</b></td>"
            f"<td>{_e(broken)}</td><td>{_e(coverage)}</td><td>{_e(FIELD_CODES[field])}</td></tr>"
        )
    return "\n".join(out)


def load_rows(path: Path) -> list[dict[str, Any]]:
    lines = path.read_text(encoding="utf-8").splitlines()
    return [json.loads(line) for line in lines if line.strip()]


#: علامةُ الإدراج في القالب: `@@مفتاح@@` — لا `str.format` فأقواسُ CSS تبقى كما هي.
MARKER = re.compile(r"@@([a-z0-9_]+)@@")


def _settings(rows: list[Mapping[str, Any]]) -> dict[str, str]:
    """إعدادُ القياس من السطور نفسها: قيمةٌ واحدةٌ متّفقة، أو كلُّ القيم المختلفة إن تعدّدت."""

    def one(key: str) -> str:
        found = sorted({str(r.get(key)) for r in rows})
        return " / ".join(found)

    stamps = sorted(str(r.get("finished_at")) for r in rows)
    return {
        "database": one("database"),
        "teachers": one("teachers"),
        "seconds_cap": one("seconds_cap"),
        "quality_cap": one("quality_cap"),
        "seed": one("seed"),
        "workers": one("workers"),
        "period": f"{stamps[0]} — {stamps[-1]}",
    }


def render(rows: list[dict[str, Any]], sections: Mapping[str, str]) -> str:
    """يملأ القالب؛ ومفتاحٌ في القالب بلا قيمةٍ خطأٌ صريح لا خانةٌ فارغة."""
    base = Baseline.of(rows)
    template = (Path(__file__).with_name("pref_impact_report.html")).read_text(encoding="utf-8")
    values: dict[str, str] = {
        "base_hc5": _e(base.hc5),
        "base_hc22": _e(base.hc22),
        "band5": _e(base.band5),
        "band22": _e(base.band22),
        "base_runs": _e(base.runs),
        "runs": _e(len(rows)),
        "thresholds": threshold_rows(rows, base),
        "scenarios": scenario_rows(rows, base),
        **{k: _e(v) for k, v in _settings(rows).items()},
        **sections,
    }
    missing = sorted(set(MARKER.findall(template)) - set(values))
    if missing:
        raise KeyError("مفاتيحُ بلا قيمة في القالب: " + "، ".join(missing))
    return MARKER.sub(lambda m: values[m.group(1)], template)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="تقريرُ أثر تفضيلات المعلّمين (HTML)")
    parser.add_argument("runs", type=Path)
    parser.add_argument("--sections", type=Path, help="JSON: نصوصُ الخلاصة والتوصية (HTML مأمون)")
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    sections = json.loads(args.sections.read_text(encoding="utf-8")) if args.sections else {}
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(render(load_rows(args.runs), sections), encoding="utf-8")
    print(args.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

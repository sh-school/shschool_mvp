"""إحصاءُ الغياب بالطلبة لا بالسجلات: مرحلة ← جناح ← شعبة، بنسب غيابٍ فقط (W-20261020-005 الخطوة 4).

طبقةُ تجميعٍ **فوق** `ministry_selectors.ministry_summary` نفسِه (إعادةُ استعمالٍ لا منطقٌ ثانٍ)، فالأرقامُ تطابق
شاشةَ الوزارة حرفياً: الوحدةُ الطالبُ الذي غاب الحصّتين الأولى والثانية معاً، والمقامُ **كلُّ المقيَّدين**.

* الجناحُ 3 جناحٌ واحدٌ بنسبةٍ إجماليّة وسطرين فرعيّين (إعدادي / ثانوي) لأنّه يعبر مرحلتين.
* شُعبُ التربية الخاصّة (بلا جناحٍ بقرار) بندٌ مستقلٌّ «خارج الأجنحة» فلا يختلف مجموعُ الأجنحة عن المدرسة بلا تفسير.
* لا رقمَ شخصيّاً ولا أسماءَ في المخرَج: أعدادٌ ونسبٌ فقط.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .ministry_selectors import ClassRow, Counts, MinistrySummary

OUTSIDE_LABEL = "خارج الأجنحة"
LEVEL_LABELS = {"prep": "المرحلة الإعدادية (7–9)", "sec": "المرحلة الثانوية (10–12)"}
LEVEL_SHORT = {"prep": "إعدادي", "sec": "ثانوي"}


def rate(absent: int, enrolled: int) -> float:
    """نسبةُ الغياب المئويّة بمقام كلّ المقيَّدين، مقرّبةً لمنزلةٍ واحدة؛ مقامٌ صفرٌ = صفر."""
    return round(100 * absent / enrolled, 1) if enrolled else 0.0


@dataclass
class StatLine:
    label: str
    enrolled: int = 0
    absent_both: int = 0
    #: رمز الشعبة أو المفتاح الثابت للسطر — لا يُعرض اسمَ طالب.
    key: str = ""
    children: list[StatLine] = field(default_factory=list)

    @property
    def rate(self) -> float:
        return rate(self.absent_both, self.enrolled)

    def add(self, counts: Counts) -> None:
        self.enrolled += counts.enrolled
        self.absent_both += counts.absent_both


@dataclass
class AbsenceStats:
    school: StatLine
    stages: list[StatLine]
    wings: list[StatLine]
    outside: StatLine | None

    @property
    def bars(self) -> list[StatLine]:
        """سطورُ الرسم البيانيّ: المراحل ثم الأجنحة ثم «خارج الأجنحة»."""
        return [*self.stages, *self.wings, *([self.outside] if self.outside else [])]


def _wing_of(row: ClassRow) -> Any:
    return getattr(row.group, "wing", None)


def _line_for(rows: list[ClassRow], label: str, key: str, *, split_levels: bool) -> StatLine:
    line = StatLine(label, key=key)
    by_level: dict[str, StatLine] = {}
    for row in rows:
        if not row.has_periods and not row.counts.enrolled:
            continue
        line.add(row.counts)
        child = StatLine(row.group.short_code, key=row.group.short_code)
        child.add(row.counts)
        if split_levels:
            level = getattr(row.group, "level_type", "")
            sub = by_level.setdefault(level, StatLine(LEVEL_SHORT.get(level, level), key=level))
            sub.add(row.counts)
            sub.children.append(child)
        else:
            line.children.append(child)
    if split_levels:
        line.children = [by_level[k] for k in ("prep", "sec") if k in by_level]
        line.children += [v for k, v in by_level.items() if k not in ("prep", "sec")]
    return line


def absence_stats(summary: MinistrySummary) -> AbsenceStats:
    """يجمّع ملخّصَ الوزارة إلى مرحلة ← جناح ← شعبة، بالنطاق الذي بني عليه الملخّص."""
    rows = summary.class_rows
    school = StatLine("المدرسة", key="school")
    for row in rows:
        school.add(row.counts)

    stages: list[StatLine] = []
    for level in ("prep", "sec"):
        part = [r for r in rows if getattr(r.group, "level_type", "") == level]
        if part:
            stage = StatLine(LEVEL_LABELS[level], key=level)
            for row in part:
                stage.add(row.counts)
            stages.append(stage)

    wings_rows: dict[str, list[ClassRow]] = {}
    wing_by_code: dict[str, Any] = {}
    outside_rows: list[ClassRow] = []
    for row in rows:
        wing = _wing_of(row)
        if wing is None:
            outside_rows.append(row)
        else:
            wing_by_code[wing.code] = wing
            wings_rows.setdefault(wing.code, []).append(row)

    wings: list[StatLine] = []
    for code in sorted(wings_rows, key=lambda c: (wing_by_code[c].order, wing_by_code[c].name)):
        wing = wing_by_code[code]
        part = wings_rows[code]
        levels = {getattr(r.group, "level_type", "") for r in part}
        wings.append(_line_for(part, wing.name, f"wing-{wing.code}", split_levels=len(levels) > 1))

    outside = (
        _line_for(outside_rows, OUTSIDE_LABEL, "outside", split_levels=False)
        if outside_rows
        else None
    )
    return AbsenceStats(school, stages, wings, outside)

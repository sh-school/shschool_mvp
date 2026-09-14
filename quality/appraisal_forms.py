"""
quality/appraisal_forms.py
━━━━━━━━━━━━━━━━━━━━━━━━━━
الاستماراتُ الوزاريّةُ السبع لتقييم أداء الموظّفين — قراءةٌ لا منطقَ فيها.

البياناتُ في `quality/ministry_appraisal_forms.json`، منسوخةٌ من جداول
`AAdocs/ministry_data/2026_2027/06_attendance_performance_review.md` §2.3–2.9.
وكونُها ملفَّ بياناتٍ لا قاموسَ بايثون مقصود: الاختبارُ يقرأ المرجعَ نفسَه ويقارنه
بهذا الملفّ خانةً بخانة (`tests/test_ministry_appraisal_forms.py`)، فأيُّ
حرفٍ يُحرَّف في أحدهما يُسقط البناء.

وكلُّ استمارةٍ تذكر الأدوارَ التي تنطبق عليها بمفتاح `Role.name` وبنصِّ خانتها في
رأس الاستمارة حرفيّاً؛ وما في الرأس ولا دورَ له في المنصّة يُحفظ في
`unmapped_categories` ليُرى لا ليُخمَّن.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import cache
from pathlib import Path
from typing import Any

DATA_FILE = Path(__file__).resolve().parent / "ministry_appraisal_forms.json"


@dataclass(frozen=True)
class Indicator:
    """مؤشّرٌ فرعيٌّ بدرجته كما طُبع في الاستمارة."""

    code: str
    label: str
    score: int


@dataclass(frozen=True)
class Axis:
    """مجالٌ رئيسيٌّ بوزنه — أو عنصرٌ مسطَّحٌ بدرجته في استمارة الفئة العمالية."""

    key: str
    label: str
    weight: int
    indicators: tuple[Indicator, ...]


@dataclass(frozen=True)
class AppraisalForm:
    code: str
    section: str
    title: str
    source_file: str
    roles: tuple[tuple[str, str], ...]
    unmapped_categories: tuple[str, ...]
    axes: tuple[Axis, ...]

    @property
    def role_names(self) -> tuple[str, ...]:
        return tuple(name for name, _text in self.roles)

    @property
    def total_weight(self) -> int:
        return sum(a.weight for a in self.axes)


def _parse(raw: dict[str, Any]) -> AppraisalForm:
    return AppraisalForm(
        code=raw["code"],
        section=raw["section"],
        title=raw["title"],
        source_file=raw["source_file"],
        roles=tuple(raw["roles"].items()),
        unmapped_categories=tuple(raw["unmapped_categories"]),
        axes=tuple(
            Axis(
                key=a["key"],
                label=a["label"],
                weight=a["weight"],
                indicators=tuple(Indicator(**i) for i in a["indicators"]),
            )
            for a in raw["axes"]
        ),
    )


@cache
def load_forms() -> tuple[AppraisalForm, ...]:
    """الاستماراتُ السبع بترتيب المرجع."""
    data = json.loads(DATA_FILE.read_text(encoding="utf-8"))
    return tuple(_parse(f) for f in data["forms"])


@cache
def forms_by_role() -> dict[str, AppraisalForm]:
    """`Role.name` ← استمارتُه. الدورُ في استمارتين خطأٌ في البيانات لا اختيار."""
    mapping: dict[str, AppraisalForm] = {}
    for form in load_forms():
        for role_name in form.role_names:
            if role_name in mapping:
                raise ValueError(
                    f"الدور {role_name} في استمارتين: {mapping[role_name].code} و{form.code}"
                )
            mapping[role_name] = form
    return mapping

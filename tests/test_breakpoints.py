"""[CSS] سلّمُ نقاط الكسر — كلُّ عرضٍ في `@media`/`@container` من نقطةٍ في السلّم أو استثناءٍ مسوَّغٍ معدود.

أبلغ التدقيقُ (2026-10-14، التوصية 3) أنّ نقاط الكسر مبعثرةٌ، فكلّما كتب مطوّرٌ استعلاماً اختار رقماً من
رأسه. وقاس 0424 الأساسَ على main فوجد 15 قيمة عرضٍ مميّزة في 120 استعلاماً؛ وحين أُعيد القياس على
الحزمة الحاليّة (بعد تقسيم الجودة) كانت 13 قيمة. والسلّمُ الذي يقوم عليه الحارس:

* **640** — حدّ الجوّال: `max-width: 640px` للجوّال، و`min-width: 641px` لما فوقه.
* **768** — اللوحيّ: `max-width: 767px` دون اللوحيّ، و`min-width: 768px` منه فصاعداً.
* **1024** — المكتب: `max-width: 1024px`، و`min-width: 1025px` لما فوقه.
* **1440** — الواسع: `min-width: 1440px`.

والقيمُ المتلاصقةُ في كلّ نقطة (640/641، 767/768، 1024/1025) هي حدّا شرطين متمّمين لا نقطتان:
`max-width: 640px` و`min-width: 641px` يقسمان العرضَ نصفين لا يتداخلان ولا يتركان بكسلاً بلا حكم.

ما خرج عن السلّم ولا يزال خارجَه فهو **استثناءٌ مسوَّغٌ** في `EXCEPTIONS` بسببه وعدد مرّاته: كسورٌ يحكمها
محتوى مكوّنٍ بعينه لا عرضُ الصفحة، وتبديلُها بنقطة السلّم يحرّك الكسرَ أكثر من 40px فيتغيّر مظهرُ صفحاتٍ في
نطاقٍ كامل. وتبقى كما هي حتى تُعاد صياغتُها بـcontainer queries.

والحارس يفشل على: عرضٍ خارج السلّم والاستثناءات، وعلى استثناءٍ يزيد عدد مرّاته، وعلى استثناءٍ لم يعد
مستعمَلاً (فيُحذف من القائمة)، فلا تزيد القائمة ولا تبقى مَعلَماً ميّتاً.
"""

from __future__ import annotations

import re
from collections import Counter

from tests.css_source import css_paths

#: نقاطُ السلّم، ولكلٍّ منها حدّاها المتمّمان (N وN±1) في `LADDER`.
LADDER_STEPS = (640, 768, 1024, 1440)
LADDER = frozenset({640, 641, 767, 768, 1024, 1025, 1440})

#: (الملفّ، العرض بالبكسل) ← (عدد المرّات، السبب). كلُّ استثناءٍ يبقى حتى يصير container query.
EXCEPTIONS: dict[tuple[str, int], tuple[int, str]] = {
    ("32-modules-3.css", 900): (
        1,
        "مصفوفة الجدول تُمرَّر أفقياً دون 900 وعمودا القسم والمعلّم لاصقان؛ النقطةُ قيست على عرض المصفوفة",
    ),
    ("32-modules-3.css", 1029): (
        1,
        "قرار المالك D-23: شريطُ أدوات الجدولة يلتفّ حتى 1028px ويُحمى باختبار test_mobile_layout؛ لا تُنقل إلى 1025",
    ),
    ("32-modules-3.css", 480): (1, "سقفُ عرض رسالة خطأ التوليد بالأحرف (18ch) في أضيق الجوّالات"),
    ("33-modules-4.css", 900): (
        2,
        "شارتا العمود الكاملة/القصيرة وشرطُ اللمس الخشن يحكمهما عرضُ شبكة الصفوف لا عرضُ الصفحة",
    ),
    ("33-modules-4.css", 400): (
        1,
        "شبكة أزرار الإجراءات تصير عموداً واحداً دون 400 فقط؛ بنقطة الجوّال يتغيّر النطاق 401–640",
    ),
    ("33-modules-4.css", 1100): (
        1,
        "شريطُ خمس بطاقات مؤشّر لا يتّسع تحت ≈1100px (5×200px) فيعود الالتفافُ",
    ),
    ("34-docs-viewer.css", 1100): (
        1,
        "عارض الوثائق: الشجرةُ الجانبيّة تنزل تحت المحتوى دون 1100 لا 1024",
    ),
}

_QUERY = re.compile(r"@(?:media|container)\b[^{]*\{", re.IGNORECASE)
_LEGACY = re.compile(r"\(\s*(?:min|max)-width\s*:\s*(\d+(?:\.\d+)?)px\s*\)", re.IGNORECASE)
_RANGE = re.compile(r"width\s*(?:>=|<=|>|<)\s*(\d+(?:\.\d+)?)px", re.IGNORECASE)


def _widths(text: str) -> list[int]:
    found: list[int] = []
    for head in _QUERY.findall(text):
        for raw in _LEGACY.findall(head) + _RANGE.findall(head):
            found.append(round(float(raw)))
    return found


def _usage() -> Counter[tuple[str, int]]:
    usage: Counter[tuple[str, int]] = Counter()
    for path in css_paths():
        for width in _widths(path.read_text(encoding="utf-8")):
            usage[(path.name, width)] += 1
    return usage


def test_every_width_query_is_on_the_ladder_or_a_justified_exception():
    off_ladder = {
        key: count
        for key, count in _usage().items()
        if key[1] not in LADDER and key not in EXCEPTIONS
    }

    assert not off_ladder, (
        "عرضٌ في @media/@container خارج سلّم نقاط الكسر (640/641، 767/768، 1024/1025، 1440): "
        f"{off_ladder}. استعمل أقرب نقطة من السلّم، أو أضف استثناءً مسوَّغاً في EXCEPTIONS."
    )


def test_the_exceptions_never_grow_and_are_never_dead():
    usage = _usage()
    grew = {
        key: (usage[key], allowed)
        for key, (allowed, _reason) in EXCEPTIONS.items()
        if usage[key] > allowed
    }
    dead = [key for key in EXCEPTIONS if usage[key] == 0]

    assert not grew, f"استثناءٌ زاد عدد استعماله عن المسموح (الفعليّ، المسموح): {grew}"
    assert not dead, f"استثناءٌ لم يعد مستعمَلاً — احذفه من EXCEPTIONS: {dead}"


def test_the_ladder_keeps_both_halves_of_each_pair():
    """كلُّ نقطةٍ لها حدّاها المتمّمان في السلّم فلا يغيب نصفُ الشرط."""
    assert set(LADDER_STEPS) <= LADDER
    assert {641, 767, 1025} <= LADDER

"""سلّمُ الخطوط (H-03): لا خطَّ دون `--text-xs` (12px) إلّا ما في قائمةٍ صريحة.

`--text-xs` أصغرُ درجات السلّم (`10-foundation.css`)، ولا يُعرَّف `--text-2xs` (قرارُ الخطّة).
والاستثناءُ الوحيدُ **`DECORATIVE`** دائمٌ: رموزٌ لا تُقرأ نصّاً — سهمُ القوائم `.chv`، وفاصلُ الفتات،
ووحدةُ الدونات. (كانت معها قائمةٌ مؤقّتةٌ للشبكات الكثيفة العشر انتظرت مراجعةَ المالك البصريّة قبل الرفع
وبعده؛ رُفعت كلُّها إلى `--text-xs` وحُذفت القائمة — فلا تعود.)
"""

from __future__ import annotations

import re

MIN_REM = 0.75  # 12px — `--text-xs`

DECORATIVE = (
    ".chv",
    ".bc-sep",
    ".kpi-donut-unit",
    # حرفُ نقطة التفريغ في زاوية خانة الجدول العامّ (و/إ/ق): علامةٌ لونيّةٌ لا نصّ — معناها في `title` الخانة وفي مفتاح الألوان تحت الجدول.
    ".m-exempt-dot",
)

_COMMENT = re.compile(r"/\*.*?\*/", re.S)
_BLOCK = re.compile(r"([^{}]*)\{([^{}]*)\}")
_SMALL = re.compile(r"font-size\s*:\s*(\d*\.?\d+)(rem|px)")


def _blank_comments(css: str) -> str:
    """التعليقاتُ مسافاتٌ بطولها — فتبقى المواضعُ صالحةً للكتابة على الأصل."""
    return _COMMENT.sub(lambda m: re.sub(r"[^\n]", " ", m.group(0)), css)


def _rem(value: str, unit: str) -> float:
    return float(value) / 16 if unit == "px" else float(value)


def small_declarations(css: str):
    """(المحدِّد، القيمة، بداية التصريح، نهايته) لكلّ `font-size` دون 12px."""
    for block in _BLOCK.finditer(_blank_comments(css)):
        selector = " ".join(block.group(1).split())
        for decl in _SMALL.finditer(block.group(2)):
            if _rem(decl.group(1), decl.group(2)) < MIN_REM:
                start = block.start(2) + decl.start()
                yield selector, decl.group(0), start, block.start(2) + decl.end()


def allowed(selector: str) -> str | None:
    """سببُ الاستثناء، أو None."""
    if any(mark in selector for mark in DECORATIVE):
        return "decorative"
    return None

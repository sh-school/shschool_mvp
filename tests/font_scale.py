"""سلّمُ الخطوط (H-03): لا خطَّ دون `--text-xs` (12px) إلّا ما في قائمةٍ صريحة.

`--text-xs` أصغرُ درجات السلّم (`10-foundation.css`)، ولا يُعرَّف `--text-2xs` (قرارُ الخطّة).
والاستثناءُ نوعان:

- **`DECORATIVE`** دائمٌ: رموزٌ لا تُقرأ نصّاً — سهمُ القوائم `.chv`، وفاصلُ الفتات، ووحدةُ الدونات.
- **`DENSE_PENDING`** مؤقّت: شبكاتٌ كثيفةٌ صُمّمت لعرض طلابٍ كثيرين في مساحةٍ ضيّقة، فرفعُ خطّها قد
  يكسر تخطيطَها. تبقى حتّى يراجع المالكُ لقطاتِها قبل الرفع وبعده (قرارُه 2026-09-23)، ثمّ تُحذف
  من هنا وتُرفع — والقائمةُ لا تكبر: الحارسُ يمنع إضافةَ محدِّدٍ جديد إليها.
"""

from __future__ import annotations

import re

MIN_REM = 0.75  # 12px — `--text-xs`

DECORATIVE = (".chv", ".bc-sep", ".kpi-donut-unit")

DENSE_PENDING = (
    ".kpi-donut-",  # دوناتُ لوحة المؤشّرات (analytics/kpi_dashboard.html)
    ".kpi-unavail-",
    ".exg-",  # شبكةُ التفريغات
    ".per-grid-wrap",  # بطاقاتُ رصد الحصّة لمشرف الجناح
    ".rec-row__fix",
    ".rec-row__flags",
    ".rec-pick",
    ".att-btn--tile",  # خليّةُ جدول المعلّم
    ".week-grid",  # شبكةُ الأسبوع
    ".free-slot-",  # شبكةُ الحصص الفارغة
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
    if any(mark in selector for mark in DENSE_PENDING):
        return "dense_pending"
    return None

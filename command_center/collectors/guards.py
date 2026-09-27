"""لوحةُ «الحرّاس والميزانيّات» — من الملفّات المشحونة في الصورة (`static/` و`tests/*_baseline.json`) بلا شبكة.

- **هامشُ CSS**: المصغَّرُ المشحونُ مقابلَ السقف في `tests/test_css_budget.py` (يُقرأ منه نصّاً فلا يتكرّر الرقمُ هنا). دون 512 بايتاً
  أحمرُ ودون 2KB «انتبه» — وهو المقياسُ الذي تتنافس عليه الطلباتُ (VD8: السقفُ لا يُرفع).
- **السقّاطاتُ**: أعدادٌ من خطوط الأساس (ملفّاتٌ فوق حدّ الحجم، أخطاءُ mypy، صفحاتٌ خارج أنماط التخطيط) — تُعرض ولا تُحكَم:
  السقّاطةُ تنزل ولا تصعد، وحكمُها في اختباراتها لا هنا.

قراءةُ القرص = هامشُ CSS نسبةً إلى ستّة عشر كيلوبايت («مريح»): 100 حين يتّسع، ويقترب من الصفر كلّما ضاق.
لوحةٌ بلا `tests/` في الصورة تفشل بـ`no_tests` فتبقى آخرُ قيمةٍ سليمةٍ ولا يُخترَع رقم.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from django.conf import settings

from command_center import contract
from command_center.collectors.publish import failed, publish
from core.css_files import CSS_DIR, CSS_FILES
from core.static_storage import minify_css

PANEL = "guards"
BAD_MARGIN = 512
WARN_MARGIN = 2 * 1024
COMFORT_MARGIN = 16 * 1024
_BUDGET_LINE = re.compile(r"^MAX_SHIPPED_BYTES\s*=\s*(\d+)\s*\*\s*1024\s*$", re.M)


def _budget_bytes(tests: Path) -> int | None:
    match = _BUDGET_LINE.search((tests / "test_css_budget.py").read_text(encoding="utf-8"))
    return int(match.group(1)) * 1024 if match else None


def _shipped_css_bytes(root: Path) -> int:
    return sum(
        len(minify_css((root / "static" / CSS_DIR / name).read_text(encoding="utf-8")).encode())
        for name in CSS_FILES
    )


def _load(tests: Path, name: str) -> Any:
    return json.loads((tests / name).read_text(encoding="utf-8"))


def margin_level(margin: int) -> str:
    if margin < BAD_MARGIN:
        return contract.BAD
    return contract.WARN if margin < WARN_MARGIN else contract.OK


def collect() -> None:
    root = Path(settings.BASE_DIR)
    tests = root / "tests"
    try:
        budget = _budget_bytes(tests)
        oversize = _load(tests, "file_size_baseline.json")
        mypy = _load(tests, "mypy_ratchet_baseline.json")
        layouts = _load(tests, "page_layout_baseline.json")
        shipped = _shipped_css_bytes(root)
    except (OSError, ValueError):
        failed(PANEL, "no_tests")
        return
    if budget is None or not isinstance(oversize, dict) or not isinstance(mypy, dict):
        failed(PANEL, "unreadable")
        return
    margin = budget - shipped
    mypy_files = mypy.get("files", {})
    publish(
        PANEL,
        status=margin_level(margin),
        headline=f"هامشُ CSS المشحون {margin:,} بايتاً",
        gauge=100 * max(margin, 0) / COMFORT_MARGIN,
        detail=f"المشحون {shipped:,} من {budget:,} بايتاً (المصغَّر)",
        metrics=(
            ("ملفّاتٌ فوق حدّ الحجم", len(oversize)),
            ("أخطاء mypy المسجَّلة", sum(v for v in mypy_files.values() if isinstance(v, int))),
            ("صفحاتٌ خارج التخطيط", len(layouts) if isinstance(layouts, list) else "؟"),
        ),
    )

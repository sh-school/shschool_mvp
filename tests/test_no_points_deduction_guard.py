"""W-20261013-010: حارسٌ يمنع عودة نظام حسم درجات السلوك (لا أصلَ له في لوائح الوزارة).

قرارُ المالك 2026-10-13: لا نقاطَ ولا حسمَ ولا «مؤشّرَ سلوك» مشتقّاً منها. تبقى أعمدةُ
`points` و`points_deducted` و`points_restored` وجدولُ `BehaviorPointRecovery` في النماذج
والهجرات وحدَها حتى المرحلة 2 (حذفُها بقول المالك)؛ وما عداها ممنوعٌ في الشيفرة والقوالب.
"""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCAN_DIRS = (
    "behavior",
    "reports",
    "academic_management",
    "parents",
    "student_affairs",
    "api",
    "templates",
)
ALLOWED = {
    "behavior/models.py",  # الأعمدة الخاملة حتى المرحلة 2
    "core/models/__init__.py",
    "core/tenancy.py",
}
FORBIDDEN = re.compile(
    r"POINTS_BY_LEVEL|points_deducted|points_restored|BehaviorPointRecovery|net_score"
    r"|_SEVERITY_PER_LEVEL|get_student_score_pdf"
    r"|حسم من درجات السلوك|يُحسم من درجة|نقاط مخصومة|combined_score"
)


def _files():
    for d in SCAN_DIRS:
        for p in (ROOT / d).rglob("*"):
            if p.suffix in {".py", ".html", ".txt", ".js"} and "migrations" not in p.parts:
                yield p


def test_no_points_deduction_in_code_or_templates():
    hits = []
    for p in _files():
        rel = p.relative_to(ROOT).as_posix()
        if rel in ALLOWED:
            continue
        for n, line in enumerate(p.read_text(encoding="utf-8", errors="ignore").splitlines(), 1):
            if FORBIDDEN.search(line):
                hits.append(f"{rel}:{n}: {line.strip()[:90]}")
    assert not hits, "عاد حسمُ الدرجات (W-20261013-010):\n" + "\n".join(hits)

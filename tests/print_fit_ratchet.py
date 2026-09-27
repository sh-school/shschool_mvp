"""سقّاطةُ القصّ في مسارات PDF — «لا قصَّ صامتاً أبداً» (المواصفة §٣-١ خطوة 8 و§٨-٤/٥).

نصٌّ يُقطع في المطبوع هو معلومةٌ تضيع بلا خطأ: `truncatechars` و`text-overflow: ellipsis` و`-webkit-line-clamp` و`overflow: hidden` مع ارتفاعٍ محدود.
كان في القوالب أربعةُ مواضعَ (المواصفة ١-٤: `behavior/pdf/student_report.html` و`schedule/pdf/week_grid_css.html` و`schedule/print_schedule.html`)؛
والمحرّكُ (`core/print_fit`) لا يقصّ: يُصغّر بنصف نقطةٍ ثمّ «تتمّةً» ثمّ يفشل بصوتٍ عالٍ. فقوالبُ PDF:

- **لا تزيد** مواضعُ القصّ في أيّ ملفٍّ عن رقمه في `pdf_fit_baseline.json["clipping_sites"]`، وملفٌّ جديدٌ رقمُه صفر.
- **وما نقص يُسجَّل** (`python -m tests.print_fit_ratchet --update`) فلا يُستهلك الفرقُ لاحقاً — وترحيلُ قالبٍ إلى المحرّك هو الطريقُ لتنزيل الرقم.

قوالبُ PDF = ما مساره فيه `/pdf/` أو اسمُه فيه `pdf` أو `print_`، أو فيه `@page` أو `weasyprint` (تعريفُ صفحةٍ مطبوعة).
"""

from __future__ import annotations

import json
import pathlib
import re
import sys
from typing import Any

ROOT = pathlib.Path(__file__).resolve().parent.parent
BASELINE = ROOT / "tests" / "pdf_fit_baseline.json"

#: المكوّنُ المركزيّ للإطار مستثنًى: تذييلُه صفٌّ واحدٌ ثابتُ الارتفاع بـ`overflow: hidden` **شبكةَ أمانٍ فقط** — خطّةُ التذييل (`footer_plan`) تُسقط ما لا يسع
#: بالأولويّة، والملزِمُ الذي لا يسع يُعلَّم `data-overflow` لا يُقصّ (`tests/test_print_frame_render.py`).
EXEMPT = ("templates/components/print/",)

#: مواضعُ القصّ (سطرٌ فيه أحدُها = موضعٌ واحد).
_CLIP = re.compile(
    r"truncatechars|truncatewords|text-overflow|line-clamp|overflow\s*:\s*hidden", re.IGNORECASE
)
_PRINT_MARK = re.compile(r"@page|weasyprint", re.IGNORECASE)


def _is_pdf_template(path: pathlib.Path, text: str) -> bool:
    rel = path.relative_to(ROOT).as_posix()
    name = path.name
    if rel.startswith(EXEMPT):
        return False
    return (
        "/pdf/" in rel
        or "pdf" in name
        or name.startswith("print_")
        or bool(_PRINT_MARK.search(text))
    )


def count_clipping_sites() -> dict[str, int]:
    """{قالب PDF: عددُ مواضع القصّ} — الأصفارُ لا تُدرَج."""
    found: dict[str, int] = {}
    for path in sorted((ROOT / "templates").rglob("*.html")):
        text = path.read_text(encoding="utf-8", errors="ignore")
        if not _is_pdf_template(path, text):
            continue
        n = sum(1 for line in text.splitlines() if _CLIP.search(line))
        if n:
            found[path.relative_to(ROOT).as_posix()] = n
    return found


def baseline() -> dict[str, Any]:
    return json.loads(BASELINE.read_text(encoding="utf-8"))


def compare() -> tuple[list[str], list[str]]:
    """(زياداتٌ عن الخطّ، نقصاتٌ لم تُسجَّل)."""
    now, then = count_clipping_sites(), baseline()["clipping_sites"]
    grew = [f"{f}: {now[f]} > {then.get(f, 0)}" for f in sorted(now) if now[f] > then.get(f, 0)]
    dropped = [f"{f}: {now.get(f, 0)} < {then[f]}" for f in sorted(then) if now.get(f, 0) < then[f]]
    return grew, dropped


if __name__ == "__main__" and "--update" in sys.argv:
    data = baseline()
    data["clipping_sites"] = count_clipping_sites()
    BASELINE.write_text(
        json.dumps(data, ensure_ascii=False, indent=1, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(
        f"كُتب {BASELINE.name}: مواضعُ قصٍّ {sum(data['clipping_sites'].values())} في {len(data['clipping_sites'])} ملفّاً"
    )

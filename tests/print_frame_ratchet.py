"""سقّاطةُ الإطار المطبوع المركزيّ — الترويسةُ والتذييلُ المتكرّران في مكوّنٍ واحد لا في كلّ قالب (المواصفة ٥-٤).

كان لكلّ قالب PDF ترويستُه وتذييلُه بأرقامه: خمسُ نسخٍ متباينة (`core/pdf_utils.py`، `reports/base_qatar_report.html`،
`schedule/print_pages.html`، `wings/register_pdf.html`، وقالبُ الزيارة)، فلا يعرف المحرّكُ ما يتبقّى للمتن ويخرج التذييلُ سطرين بخطٍّ 6–8pt.
فالإطارُ الآن `core/print_frame.py` والمكوّناتُ `templates/components/print/` ووسومُها `core/templatetags/print_frame.py` — وما عداها **ممنوعٌ**:

- **مواضعُ الإطار:** سطرٌ فيه `running(` أو `@bottom-` (تعريفُ تذييلٍ/ترويسةٍ جاريةٍ في قالبٍ) — خطُّ الأساس 14 موضعاً في 5 ملفّات.
- **أصنافُ التذييل:** `sheet-footer` و`wp-page-footer` و`doc-footer` و`report-footer` و`page-footer` و`print-footer` خارجَ المكوّن.

**سقّاطةٌ تنزل ولا تزيد:** كلُّ ملفٍّ لا يتجاوز رقمَه في `print_frame_baseline.json`، وملفٌّ جديدٌ رقمُه صفر؛ ومن أنقص نسخةً يخفض الخطَّ في الطلب نفسه
(`python -m tests.print_frame_ratchet --update`) فلا يُستهلك الفرقُ لاحقاً. وترحيلُ قالبٍ إلى المكوّن هو الطريقُ الوحيد لتنزيل الرقم.
"""

from __future__ import annotations

import json
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
BASELINE = ROOT / "tests" / "print_frame_baseline.json"

#: ما يجري فحصُه: قوالبُ الطباعة وإطارُ `core/pdf_utils.py` الافتراضيّ (وهو آخرُ نسخةٍ تُحذف، ش7).
SCAN_GLOBS = ("templates/**/*.html", "core/pdf_utils.py")

#: المكوّنُ المركزيّ — المكانُ الوحيدُ المسموحُ فيه بهذه العلامات.
ALLOWED = (
    "core/print_frame.py",
    "core/templatetags/print_frame.py",
    "templates/components/print/",
)

_POSITION = re.compile(r"running\(|@bottom-")
_FOOTER_CLASS = re.compile(
    r"(?<![A-Za-z0-9_-])(?:sheet-footer|wp-page-footer|doc-footer|report-footer|page-footer|print-footer)(?![A-Za-z0-9_-])"
)


def _files() -> list[pathlib.Path]:
    found: set[pathlib.Path] = set()
    for pattern in SCAN_GLOBS:
        found.update(p for p in ROOT.glob(pattern) if p.is_file())
    return sorted(found)


def _allowed(rel: str) -> bool:
    return any(rel == a or (a.endswith("/") and rel.startswith(a)) for a in ALLOWED)


def count() -> dict[str, dict[str, int]]:
    """{ "positions": {ملفّ: عدد}, "footer_classes": {ملفّ: عدد} } — الأصفارُ لا تُدرَج."""
    positions: dict[str, int] = {}
    classes: dict[str, int] = {}
    for path in _files():
        rel = path.relative_to(ROOT).as_posix()
        if _allowed(rel):
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        lines = text.splitlines()
        n_pos = sum(1 for line in lines if _POSITION.search(line))
        n_cls = sum(len(_FOOTER_CLASS.findall(line)) for line in lines)
        if n_pos:
            positions[rel] = n_pos
        if n_cls:
            classes[rel] = n_cls
    return {"positions": positions, "footer_classes": classes}


def baseline() -> dict[str, dict[str, int]]:
    return json.loads(BASELINE.read_text(encoding="utf-8"))


def compare(kind: str) -> tuple[list[str], list[str]]:
    """(زياداتٌ عن الخطّ، نقصاتٌ لم تُسجَّل) لنوعٍ واحد."""
    now, then = count()[kind], baseline()[kind]
    grew = [f"{f}: {now[f]} > {then.get(f, 0)}" for f in sorted(now) if now[f] > then.get(f, 0)]
    dropped = [f"{f}: {now.get(f, 0)} < {then[f]}" for f in sorted(then) if now.get(f, 0) < then[f]]
    return grew, dropped


if __name__ == "__main__" and "--update" in sys.argv:
    data = count()
    BASELINE.write_text(
        json.dumps(data, ensure_ascii=False, indent=1, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(
        f"كُتب {BASELINE.name}: مواضعُ {sum(data['positions'].values())} في {len(data['positions'])} ملفّاً، "
        f"وأصنافُ تذييلٍ {sum(data['footer_classes'].values())} في {len(data['footer_classes'])} ملفّاً"
    )

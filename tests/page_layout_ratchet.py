"""سقّاطةُ أنماط التخطيط (LAY-03، قرار D-16) — كلُّ صفحةٍ جديدةٍ تعلن نمطَها.

الصفحةُ قالبٌ تنتهي سلسلةُ وراثته عند `base/base.html`، وإعلانُها
`{% block main_class %}{% page_layout "list" %}{% endblock %}` (في القالب أو أحد آبائه).
الصفحاتُ التي سبقت الحارسَ مسجَّلةٌ في `page_layout_baseline.json` وتُرحَّل في موجات VI-24؛
فلا يُضاف إليها اسمٌ، ومن أعلن نمطَه يُحذف منها.

    python -m tests.page_layout_ratchet --update   # يعيد كتابة الخطّ الأساس بعد الترحيل
"""

import json
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
TEMPLATES = ROOT / "templates"
BASELINE = ROOT / "tests" / "page_layout_baseline.json"
BASE = "base/base.html"

_EXTENDS = re.compile(r"\{%\s*extends\s+[\"']([^\"']+)[\"']")
_DECLARED = re.compile(r"\{%\s*page_layout\s")


def _templates() -> dict[str, str]:
    return {
        p.relative_to(TEMPLATES).as_posix(): p.read_text(encoding="utf-8")
        for p in sorted(TEMPLATES.rglob("*.html"))
    }


def _chain(name: str, tpl: dict[str, str]) -> list[str]:
    """القالبُ فآباؤه حتى الجذر."""
    chain: list[str] = []
    while name in tpl and name not in chain:
        chain.append(name)
        parent = _EXTENDS.search(tpl[name])
        if not parent:
            break
        name = parent.group(1)
    return chain


def pages() -> dict[str, bool]:
    """كلُّ صفحةٍ ← هل أعلنت نمطَها."""
    tpl = _templates()
    result = {}
    for name in tpl:
        chain = _chain(name, tpl)
        if name == BASE or not chain or _EXTENDS.search(tpl[chain[-1]]):
            continue
        if chain[-1] != BASE:
            continue
        result[name] = any(_DECLARED.search(tpl[t]) for t in chain if t != BASE)
    return result


def undeclared() -> list[str]:
    return sorted(name for name, ok in pages().items() if not ok)


def compare(baseline: list[str], current: list[str]) -> tuple[list[str], list[str]]:
    """(صفحاتٌ جديدةٌ بلا نمط، أسماءٌ في الخطّ الأساس أعلنت نمطَها أو لم تعد موجودة)."""
    known = set(baseline)
    now = set(current)
    return sorted(now - known), sorted(known - now)


if __name__ == "__main__" and "--update" in sys.argv:
    BASELINE.write_text(
        json.dumps(undeclared(), ensure_ascii=False, indent=1) + "\n", encoding="utf-8"
    )
    print(f"كُتب {BASELINE.name}: {len(undeclared())} صفحةً لم تعلن نمطَها بعد")

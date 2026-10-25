"""حارسٌ نصّيٌّ: لا أصنافَ Tailwind في قوالب `templates/dashboard/` (W-20261010-039، ردّ 0419).

لوحاتُ الأدوار تُبنى بمكوّنات المنصّة ورموزها (`ui.py` و`custom/`)؛ وأصنافُ Tailwind تعيد التخطيطَ المحلّيّ الذي أُزيل.
"""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DASHBOARD_TEMPLATES = ROOT / "templates" / "dashboard"

TAILWIND = re.compile(
    r"^(?:(?:sm|md|lg|xl|hover|focus|dark):)?"
    r"(?:flex|grid|block|inline-flex|hidden|divide-y|transition|truncate|w-full|h-full"
    r"|(?:items|justify|self)-[a-z]+|(?:gap|space-[xy]|[pm][xytblrse]?|rounded|border|w|h|min-w|max-w|col-span|grid-cols)-[\w\[\]./%-]+"
    r"|text-(?:xs|sm|base|lg|xl|[2-9]xl|center|start|end)|font-(?:bold|semibold|medium|normal))$"
)
CLASS_ATTR = re.compile(r'\bclass="([^"]*)"')


def _classes(text: str):
    for attr in CLASS_ATTR.findall(text):
        attr = re.sub(r"\{%.*?%\}|\{\{.*?\}\}", " ", attr)
        yield from attr.split()


def test_no_tailwind_classes_in_dashboard_templates():
    offenders = {}
    for path in sorted(DASHBOARD_TEMPLATES.rglob("*.html")):
        found = sorted({c for c in _classes(path.read_text(encoding="utf-8")) if TAILWIND.match(c)})
        if found:
            offenders[str(path.relative_to(ROOT))] = found
    assert not offenders, f"أصنافُ Tailwind في قوالب اللوحات (استعمل مكوّنات المنصّة): {offenders}"

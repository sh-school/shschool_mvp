#!/usr/bin/env python3
"""يولّد `.claude/rules/identity-reference.md` من مصادر الهويّة الحيّة (W-20261011-001).

الملفُّ يُحمَّل تلقائياً حين تلمس جلسةٌ `static/` أو `templates/` (ترويسة `paths`)، فيرى مَن يعدّل
الواجهةَ ألوانَ المنصّة وأيقوناتِها وأنماطَ صفحاتها دون صفحاتِ `styleguide/` المحميّة بحساب مطوّر.
لا يُحرَّر يدويّاً: `tests/test_identity_reference_fresh.py` يسقط إن تقادم عن مصادره.

الاستعمال:   python scripts/gen_identity_reference.py          (يكتب الملف)
             python scripts/gen_identity_reference.py --check  (يخرج 1 إن تقادم)
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core.icons import GROUPS, ICONS  # noqa: E402
from tests.css_source import read_css  # noqa: E402

OUT = ROOT / ".claude" / "rules" / "identity-reference.md"
LAYOUTS_DOC = ROOT / "docs" / "design" / "page_layouts.md"

_COMMENT = re.compile(r"/\*.*?\*/", re.S)
_ROOT_BLOCK = re.compile(r"(?<![\w.#-]):root\s*\{([^}]*)\}")
_DARK_BLOCK = re.compile(r"html\.dark\s*\{([^}]*)\}")
_DECL = re.compile(r"--([A-Za-z0-9_-]+)\s*:\s*([^;]+);")
_COLOUR = re.compile(r"^(?:#[0-9A-Fa-f]{3,8}|rgba?\(|hsla?\(|color-mix\(|var\(\s*--)")
#: مجموعاتُ اللوحة بالبادئة — مطابقةٌ لما يعرضه دليلُ الهويّة (core/styleguide.py).
GROUP_PREFIXES = (
    ("الهويّة", ("maroon", "gold", "skyline", "palm", "sea")),
    ("النصّ والأسطح", ("text", "border", "surface", "page-bg", "on-fill", "focus-color")),
    ("الترويسة والقائمة والذيل", ("header", "nav", "footer", "menu")),
    ("الحالات", ("status", "neutral-solid")),
    ("ألوان التمييز", ("accent",)),
    ("الرسوم البيانيّة", ("chart", "ring-track")),
    ("الأدوار والوحدات", ("role", "q", "swap")),
)


def _decls(blocks: list[str]) -> dict[str, str]:
    out: dict[str, str] = {}
    for block in blocks:
        for name, value in _DECL.findall(block):
            out.setdefault(name, " ".join(value.split()))
    return out


def _in_group(name: str, prefixes: tuple[str, ...]) -> bool:
    return any(name == p or name.startswith(p + "-") for p in prefixes)


def colour_tables() -> list[str]:
    css = _COMMENT.sub("", read_css())
    light = _decls(_ROOT_BLOCK.findall(css))
    dark = _decls(_DARK_BLOCK.findall(css))
    names = [n for n, v in light.items() if _COLOUR.match(v)]
    lines: list[str] = []
    placed: set[str] = set()
    for label, prefixes in (*GROUP_PREFIXES, ("أخرى", None)):
        group = [n for n in names if n not in placed and (prefixes is None or _in_group(n, prefixes))]
        if not group:
            continue
        placed.update(group)
        lines += [f"### {label}", "", "| الرمز | نهاراً | ليلاً |", "|---|---|---|"]
        lines += [f"| `--{n}` | `{light[n]}` | {('`' + dark[n] + '`') if n in dark else '—'} |" for n in group]
        lines.append("")
    return lines


def icon_lines() -> list[str]:
    lines: list[str] = []
    for group, label in GROUPS.items():
        items = [f"`{key}` {spec.label}" for key, spec in ICONS.items() if spec.group == group]
        if items:
            lines += [f"**{label}** ({len(items)}): " + "؛ ".join(items), ""]
    return lines


def layout_lines() -> list[str]:
    text = LAYOUTS_DOC.read_text(encoding="utf-8")
    lines = [
        f"- `{m.group(2)}` ({m.group(1)}): {m.group(3).strip()}"
        for m in re.finditer(r"^### 7\.\d+ (.+?) — `(layout-[a-z]+)`\n\n- \*\*الغرض:\*\* (.+)$", text, re.M)
    ]
    return [*lines, ""]


def build() -> str:
    head = [
        "---",
        "paths:",
        '  - "static/**"',
        '  - "templates/**"',
        '  - "core/templatetags/ui.py"',
        '  - "core/icons.py"',
        "---",
        "",
        "# مرجعُ الهويّة المولَّد: الألوان والأيقونات وأنماط الصفحات",
        "",
        "> مولَّدٌ آليّاً من `static/css/custom/` و`core/icons.py` و`docs/design/page_layouts.md` — لا يُحرَّر بيدٍ؛ "
        "أعِد توليده بـ`python scripts/gen_identity_reference.py`. يقوم مقامَ صفحات `/styleguide/` لمن لا حسابَ مطوّر له.",
        '> القاعدة: لونٌ برمزٍ لا بقيمة، وأيقونةٌ بمعناها `{% icon "المفتاح" %}`، وصفحةٌ بنمطٍ مسمّى `{% page_layout "…" %}`.',
        "",
        "## أنماط الصفحات السبعة",
        "",
    ]
    colours = ["## رموز الألوان (`:root` + `html.dark`)", "", *colour_tables()]
    icons = ["## قاموس الأيقونات (بالمعنى لا بالشكل)", "", *icon_lines()]
    return "\n".join(head + layout_lines() + colours + icons).rstrip() + "\n"


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    new = build()
    if "--check" in sys.argv:
        old = OUT.read_text(encoding="utf-8") if OUT.exists() else ""
        if old != new:
            print("✘ مرجع الهويّة متقادم: شغّل python scripts/gen_identity_reference.py")
            return 1
        print("✔ مرجع الهويّة مطابقٌ لمصادره")
        return 0
    OUT.write_text(new, encoding="utf-8", newline="\n")
    print(f"✔ كُتب {OUT.relative_to(ROOT)} ({len(new.splitlines())} سطراً)")
    return 0


if __name__ == "__main__":
    sys.exit(main())

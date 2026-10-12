#!/usr/bin/env python3
"""يولّد ملفّات `.claude/rules/identity-*.md` من مصادر الهويّة الحيّة (W-20261011-001).

ثلاثةُ ملفّات لا واحد: سقّاطةُ حجم الدستور (tests/test_claude_md_size.py) تحدّ كلَّ قاعدةٍ بـ200 سطر،
وجدولُ الألوان وحدَه يتجاوزها. الأنماط والأيقونات في identity-reference.md، والألوان في ملفَّين.
الملفّاتُ تُحمَّل تلقائياً حين تلمس جلسةٌ `static/` أو `templates/` (ترويسة `paths`)، فيرى مَن يعدّل
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

RULES = ROOT / ".claude" / "rules"
OUT = RULES / "identity-reference.md"
OUT_COLOURS_CORE = RULES / "identity-colours-core.md"
OUT_COLOURS_MORE = RULES / "identity-colours-more.md"
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


def colour_tables() -> dict[str, list[str]]:
    css = _COMMENT.sub("", read_css())
    light = _decls(_ROOT_BLOCK.findall(css))
    dark = _decls(_DARK_BLOCK.findall(css))
    names = [n for n, v in light.items() if _COLOUR.match(v)]
    tables: dict[str, list[str]] = {}
    placed: set[str] = set()
    for label, prefixes in (*GROUP_PREFIXES, ("أخرى", None)):
        group = [n for n in names if n not in placed and (prefixes is None or _in_group(n, prefixes))]
        if not group:
            continue
        placed.update(group)
        lines = [f"### {label}", "", "| الرمز | نهاراً | ليلاً |", "|---|---|---|"]
        lines += [f"| `--{n}` | `{light[n]}` | {('`' + dark[n] + '`') if n in dark else '—'} |" for n in group]
        tables[label] = [*lines, ""]
    return tables


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


#: مجموعاتُ الملفّ الأوّل من الألوان؛ والباقي في الثاني.
CORE_GROUPS = ("الهويّة", "النصّ والأسطح", "الترويسة والقائمة والذيل", "الحالات")
PATHS_HEAD = [
    "---",
    "paths:",
    '  - "static/**"',
    '  - "templates/**"',
    '  - "core/templatetags/ui.py"',
    '  - "core/icons.py"',
    "---",
    "",
]
_SOURCES = "> مولَّدٌ آليّاً — لا يُحرَّر بيدٍ؛ أعِد توليده بـ`python scripts/gen_identity_reference.py`."


def build() -> dict[Path, str]:
    """المسارُ ← نصُّه، لكلّ ملفٍّ من الثلاثة."""
    tables = colour_tables()
    core = [line for label in CORE_GROUPS for line in tables.get(label, [])]
    more = [line for label, ls in tables.items() if label not in CORE_GROUPS for line in ls]
    main = [
        *PATHS_HEAD,
        "# مرجعُ الهويّة المولَّد: أنماط الصفحات والأيقونات",
        "",
        "> مولَّدٌ آليّاً من `static/css/custom/` و`core/icons.py` و`docs/design/page_layouts.md` — لا يُحرَّر بيدٍ؛ "
        "أعِد توليده بـ`python scripts/gen_identity_reference.py`. يقوم مقامَ صفحات `/styleguide/` لمن لا حسابَ مطوّر له.",
        '> القاعدة: لونٌ برمزٍ لا بقيمة، وأيقونةٌ بمعناها `{% icon "المفتاح" %}`، وصفحةٌ بنمطٍ مسمّى `{% page_layout "…" %}`.',
        "> جداولُ الألوان في `identity-colours-core.md` (الهويّة والنصّ والترويسة والحالات) و`identity-colours-more.md` (التمييز والرسوم والأدوار).",
        "",
        "## أنماط الصفحات السبعة",
        "",
        *layout_lines(),
        "## قاموس الأيقونات (بالمعنى لا بالشكل)",
        "",
        *icon_lines(),
    ]
    core_doc = [*PATHS_HEAD, "# رموزُ الألوان (1/2): الهويّة والنصّ والترويسة والحالات", "", _SOURCES,
                "> نهاراً في `:root` وليلاً في `html.dark`.", "", *core]
    more_doc = [*PATHS_HEAD, "# رموزُ الألوان (2/2): التمييز والرسوم والأدوار وغيرها", "", _SOURCES,
                "> نهاراً في `:root` وليلاً في `html.dark`.", "", *more]
    return {
        OUT: "\n".join(main).rstrip() + "\n",
        OUT_COLOURS_CORE: "\n".join(core_doc).rstrip() + "\n",
        OUT_COLOURS_MORE: "\n".join(more_doc).rstrip() + "\n",
    }


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    files = build()
    if "--check" in sys.argv:
        stale = [p for p, text in files.items() if not p.exists() or p.read_text(encoding="utf-8") != text]
        if stale:
            print("✘ مرجع الهويّة متقادم: شغّل python scripts/gen_identity_reference.py")
            return 1
        print("✔ مرجع الهويّة مطابقٌ لمصادره")
        return 0
    for path, text in files.items():
        path.write_text(text, encoding="utf-8", newline="\n")
        print(f"✔ كُتب {path.relative_to(ROOT)} ({len(text.splitlines())} سطراً)")
    return 0


if __name__ == "__main__":
    sys.exit(main())

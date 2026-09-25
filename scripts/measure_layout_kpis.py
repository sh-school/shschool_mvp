"""قياسُ مؤشّرات نظام أنماط التخطيط من الشجرة — يُعاد تشغيله عند كلّ تحديثٍ للخارطة.

    python measure_layout_kpis.py <جذر-المشروع> [--json]

يقرأ templates/** وstatic/css/custom/*.css ويحسب مؤشّرات الخارطة LK1..LK5 (بنودُها LAY-*).
تحليلٌ نصّيٌّ للقوالب لا قياسٌ مُصيَّر: مقدارُ الفراغ على الشاشة (D1/D2) يحتاج متصفّحاً
بجلسة دخول ويُقاس في VI-23، لا هنا.

قاعدةُ العدّ: «صفحة» = قالبٌ تنتهي سلسلةُ وراثته عند `base/base.html` (ما عدا `base.html` نفسه)؛
وجزئيّاتُها تُتبَع بـ`{% include %}` حتى أربعة مستويات.
"""

import glob
import json
import pathlib
import re
import sys

root = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else ".")
templates = root / "templates"

_EXTENDS = re.compile(r"\{%\s*extends\s+[\"']([^\"']+)[\"']")
_INCLUDE = re.compile(r"\{%\s*include\s+[\"']([^\"']+)[\"']")


def read(path: pathlib.Path) -> str:
    return path.read_text(encoding="utf8", errors="ignore")


tpl = {p.relative_to(templates).as_posix(): read(p) for p in sorted(templates.rglob("*.html"))}


def root_of(name: str) -> str:
    """جذرُ سلسلة الوراثة (`base/base.html` للصفحات الحيّة)."""
    seen: set[str] = set()
    while name in tpl and name not in seen:
        seen.add(name)
        parent = _EXTENDS.search(tpl[name])
        if not parent:
            return name
        name = parent.group(1)
    return name


pages = [n for n in tpl if n != "base/base.html" and root_of(n) == "base/base.html"]


def expanded(name: str, depth: int = 0, seen: set[str] | None = None) -> str:
    """نصُّ القالب مع جزئيّاته المضمَّنة (أربعة مستويات)."""
    seen = set() if seen is None else seen
    if name in seen or name not in tpl or depth > 4:
        return ""
    seen.add(name)
    text = tpl[name]
    return text + "".join(expanded(inc, depth + 1, seen) for inc in _INCLUDE.findall(text))


full = {name: expanded(name) for name in pages}
css = "\n".join(
    read(pathlib.Path(f)) for f in sorted(glob.glob(str(root / "static/css/custom/*.css")))
)

out: dict[str, float | int] = {"info_pages": len(pages)}

# LK1 — صفحاتٌ تعلن نمطَها: وسمُ `{% page_layout %}` (لا وجودَ له قبل LAY-03، فالأساس صفر).
declared = sum(1 for n in pages if re.search(r"\{%\s*page_layout\b", full[n]))
out["LK1_pages_declaring_layout_pct"] = round(100 * declared / len(pages), 1)

# LK2 — حدودُ التوقّف الفعليّة: قيمُ width في استعلامات الوسائط، والمتجاورةُ بفارق ≤1px حدٌّ واحد
# (max-width:640 وmin-width:641 حدٌّ واحد). لا تُعَدّ print وprefers-*.
widths = sorted(
    {
        int(v)
        for cond in re.findall(r"@media\s*([^{]+)\{", css)
        for v in re.findall(r"(?:min|max)-width\s*:\s*(\d+)px", cond)
    }
)
boundaries: list[int] = []
for prev, w in zip([-9, *widths], widths, strict=False):
    if w - prev > 1:
        boundaries.append(w)
out["LK2_breakpoints"] = len(boundaries)
out["info_breakpoint_values"] = ",".join(str(b) for b in boundaries)  # type: ignore[assignment]

# LK3 — تغطيةُ الحالة الفارغة في الصفحات ذات الجدول.
with_table = [n for n in pages if "<table" in full[n]]
covered = [n for n in with_table if re.search(r"empty_state|empty-state", full[n])]
out["LK3_empty_state_coverage_pct"] = round(100 * len(covered) / max(len(with_table), 1), 1)
out["info_table_pages"] = len(with_table)

# LK4 — قوالبُ لوحات الأدوار.
out["LK4_role_dashboard_templates"] = len(glob.glob(str(templates / "dashboard/roles/*.html")))

# LK5 — أسطرُ CSS محلّيٌّ مربوطٌ بقوالبَ صفحاتٍ (كتلُ «── templates/x.html ──» في ملفّات الوحدات).
marks = [(m.start(), m.group(1)) for m in re.finditer(r"/\*\s*──\s*(.+?)\s*──\s*\*/", css)]
marks.append((len(css), ""))
local_lines = 0
for (start, label), (end, _next) in zip(marks, marks[1:], strict=False):
    if any(t in pages for t in re.findall(r"templates/([\w/\-.]+\.html)", label)):
        local_lines += css[start:end].count("\n")
out["LK5_page_local_css_lines"] = local_lines

# معلومات مساعدة (لا تُسجَّل هدفاً).
out["info_exec_dash_definitions"] = len(re.findall(r"^\.exec-dash\s*\{", css, flags=re.M))
out["info_pages_with_le1_card"] = sum(
    1
    for n in pages
    if len(re.findall(r"\{%\s*section_card|class=\"[^\"]*\bcard(?:-qatar)?\b", full[n])) <= 1
)
out["info_container_queries"] = css.count("@container")

if "--json" in sys.argv:
    print(json.dumps(out, ensure_ascii=False, indent=2))
else:
    for key, value in out.items():
        print(f"{key}: {value}")

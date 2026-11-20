"""[ROADMAP] حارسُ المسارات: لا تكتب هجرةُ خارطةٍ جديدةٌ بنداً بمسارٍ لا تعرفه الصفحة.

حادثة 2026-11-20: هجراتُ مزامنةٍ (0048 إلى 0088) كتبت `security` و`operations` و`behavior` و`design` و`tools`،
والصفحةُ تبني المصفوفةَ والخطَّ الزمنيَّ من قائمة المسارات (`meta.lanes`) وحدَها، فاختفى 45 بنداً من العرض.
أصلحتها 0089، وهذا الحارسُ يقرأ كلَّ هجرةٍ بعدها قراءةً ساكنة (AST) ويجمع قيمَ المسار التي تكتبها:
`lane="…"` في استدعاء، و`"lane": "…"` في قاموس، والعنصرَ الذي يقع موقعَ `lane` في صفوف جدولٍ يُفكّ في حلقةٍ أو إسناد.
"""

import ast
from pathlib import Path

MIGRATIONS = Path(__file__).resolve().parent.parent / "roadmap" / "migrations"

#: مفاتيحُ `meta.lanes` على الإنتاج (2026-11-20). مسارٌ جديدٌ يُضاف إلى الوثيقة أوّلاً ثمّ هنا.
LANE_KEYS = frozenset(
    {"sec", "backend", "ops", "quality", "frontend", "mobile", "desktop", "debt", "product"}
)

#: آخرُ هجرةٍ قبل الحارس؛ ما قبلها مُطبَّقٌ على الإنتاج ولا يُعدَّل، وأصلحت 0089 بياناتِه.
LAST_UNGUARDED = 89


def _number(path):
    head = path.name.split("_", 1)[0]
    return int(head) if head.isdigit() else -1


def _module_constants(tree):
    out = {}
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    out[target.id] = node.value
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name) and node.value:
            out[node.target.id] = node.value
    return out


def _lane_index(target):
    if isinstance(target, (ast.Tuple, ast.List)):
        for i, elt in enumerate(target.elts):
            if isinstance(elt, ast.Name) and elt.id == "lane":
                return i
    return None


def _str_at(row, index):
    if isinstance(row, (ast.Tuple, ast.List)) and index < len(row.elts):
        elt = row.elts[index]
        if isinstance(elt, ast.Constant) and isinstance(elt.value, str):
            return elt.value
    return None


def lane_values(source):
    """قيمُ المسار النصّيّةُ التي تكتبها الهجرة."""
    tree = ast.parse(source)
    consts = _module_constants(tree)
    found = []

    def rows_of(expr):
        if isinstance(expr, ast.Name):
            expr = consts.get(expr.id)
        return expr

    for node in ast.walk(tree):
        if isinstance(node, ast.keyword) and node.arg == "lane":
            if isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
                found.append(node.value.value)
        elif isinstance(node, ast.Dict):
            for key, value in zip(node.keys, node.values, strict=False):
                if (
                    isinstance(key, ast.Constant)
                    and key.value == "lane"
                    and isinstance(value, ast.Constant)
                    and isinstance(value.value, str)
                ):
                    found.append(value.value)
        elif isinstance(node, (ast.For, ast.comprehension)):
            index = _lane_index(node.target)
            table = rows_of(node.iter) if index is not None else None
            if isinstance(table, (ast.Tuple, ast.List)):
                found += [v for row in table.elts if (v := _str_at(row, index)) is not None]
        elif isinstance(node, ast.Assign) and len(node.targets) == 1:
            index = _lane_index(node.targets[0])
            row = rows_of(node.value) if index is not None else None
            if (v := _str_at(row, index)) is not None:
                found.append(v)
    return found


def test_the_scanner_sees_every_writing_style_of_the_old_migrations():
    """لا حارسَ أجوف: يلتقط القيمَ الخاطئةَ في الهجرات القديمة بأساليبها الثلاثة."""
    read = {
        n: (MIGRATIONS / f).read_text(encoding="utf-8")
        for n, f in (
            (81, "0081_clinic_family_2026_10_20.py"),
            (85, "0085_sync_items_2026_10_26.py"),
            (88, "0088_sync_items_2026_11_20.py"),
        )
    }
    assert "operations" in lane_values(read[81])
    assert set(lane_values(read[85])) - LANE_KEYS
    assert lane_values(read[88]) == ["security"]
    assert sorted(lane_values('M.objects.create(lane="ops")\nX = {"lane": "tools"}')) == [
        "ops",
        "tools",
    ]


def test_new_roadmap_migrations_write_only_known_lanes():
    bad = {}
    for path in sorted(MIGRATIONS.glob("[0-9]*.py")):
        if _number(path) <= LAST_UNGUARDED:
            continue
        unknown = sorted(set(lane_values(path.read_text(encoding="utf-8"))) - LANE_KEYS)
        if unknown:
            bad[path.name] = unknown
    assert not bad, f"مساراتٌ لا تعرفها الصفحة (المعتمد: {sorted(LANE_KEYS)}): {bad}"

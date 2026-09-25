"""[IMPORTS] كلُّ استيرادٍ نسبيٍّ في المشروع يشير إلى وحدةٍ موجودة.

كسر تقسيمُ `operations/models.py` إلى حزمةٍ استيراداً نسبيّاً **داخل دالّة** (`from .constraint_registry import spec`
في `ScheduleConstraintOverride.clean()`): كانت النقطةُ تعني `operations` فصارت `operations.models`، والاستيرادُ
يجري وقت الاستدعاء فلا يظهر عند الإقلاع ولا في فحصٍ بنيويٍّ للأصناف — سقط 11 اختباراً بـ`ModuleNotFoundError` فقط.

هذا الحارسُ يمسح كلَّ ملفّات المشروع (`ast`، لا تنفيذ) ويتحقّق أنّ كلَّ `from .x import y` (بأيّ عمقٍ وفي أيّ موضع)
يقع على ملفٍّ أو حزمةٍ حقيقيّة. ولا يحلّ `from . import x` (لا وحدةَ مسمّاةَ فيه): أسماؤه قد تكون وحداتٍ أو سمات.
"""

import ast
import pathlib

SKIP_DIRS = {
    ".venv",
    "venv",
    "node_modules",
    "staticfiles",
    "worktrees",
    ".git",
    "site-packages",
    ".cache",
}


def _sources():
    for path in sorted(pathlib.Path(".").rglob("*.py")):
        if SKIP_DIRS & set(path.parts) or any(part.startswith(".") for part in path.parts[:-1]):
            continue
        yield path


def _unresolved(path: pathlib.Path) -> list[str]:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except (SyntaxError, UnicodeDecodeError):
        return []
    found = []
    for node in ast.walk(tree):
        if not (isinstance(node, ast.ImportFrom) and node.level > 0 and node.module):
            continue
        base = path.parent
        for _ in range(node.level - 1):
            base = base.parent
        target = base.joinpath(*node.module.split("."))
        if not (target.with_suffix(".py").is_file() or (target / "__init__.py").is_file()):
            found.append(
                f"{path.as_posix()}:{node.lineno}: from {'.' * node.level}{node.module} import …"
            )
    return found


def test_every_relative_import_points_at_a_real_module():
    broken = [line for path in _sources() for line in _unresolved(path)]

    assert not broken, "استيراداتٌ نسبيّةٌ لا وحدةَ لها:\n  " + "\n  ".join(broken)


def test_the_scan_sees_the_split_packages_and_would_catch_a_break(tmp_path):
    """حارسٌ لا يجد شيئاً ينجح صامتاً: يرى الحزمتين، ويُمسك استيراداً مكسوراً حقّاً."""
    scanned = {path.as_posix() for path in _sources()}
    assert any(p.startswith("operations/models") for p in scanned)
    assert any(p.startswith("quality/models") for p in scanned)

    package = tmp_path / "pkg"
    package.mkdir()
    (package / "__init__.py").write_text("", encoding="utf-8")
    (package / "real.py").write_text("", encoding="utf-8")
    (package / "mod.py").write_text(
        "from .real import x\ndef f():\n    from .missing import y\n", encoding="utf-8"
    )
    assert len(_unresolved(package / "mod.py")) == 1

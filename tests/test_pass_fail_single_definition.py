"""«ناجح/راسب» تعريفٌ واحد — لا نصٌّ حرفيٌّ `status="pass"` يضيع بين فرعين.

نقل wave3-e قراءاتِ النتائج السنويّة من العروض إلى `student_affairs/selectors.py`
و`core/dashboard_selectors.py` بنصّها `Q(status="pass")`. ويستبدل wave3-f النصَّ نفسَه
في مواضعه القديمة بـ`status__in=PASSING_STATUSES` (`core.domain.grades`): المُرفَّعُ ناجح،
وطالبُ الدور الثاني راسب. فإن دُمج الفرعان وحُلّ التعارضُ بأخذ المنقول، بقي التعريفُ
القديم في القارئ — وسقّاطةُ الطبقات تعدّ الاستعلامات ولا ترى الشرطَ فيها.

فهذا الحارس يعدّ المواضعَ الحرفيّة في شيفرة المشروع: ما دام التعريفُ الواحدُ غائباً
فلا تزيد على ما هي عليه اليوم (ولا تُنسخ إلى قارئٍ جديد)، ومتى حضر فلا يبقى منها شيء.
"""

from __future__ import annotations

import ast
import pathlib
from collections import Counter

ROOT = pathlib.Path(__file__).resolve().parent.parent

LITERALS = frozenset({"pass", "fail"})

#: ما ليس شيفرةَ المنصّة: الاختبارات تبني الحالاتِ بنصّها، والهجراتُ تاريخٌ لا يُعدَّل.
SKIPPED_PARTS = frozenset({"tests", "migrations", "node_modules", "staticfiles", "__pycache__"})

#: المواضعُ الحرفيّة قبل التعريف الواحد — لكلّ ملفٍّ عددُها (السطرُ يتحرّك، والعددُ لا).
BEFORE_SINGLE_DEFINITION = {
    "analytics/services.py": 3,
    "api/views.py": 2,
    "assessments/querysets.py": 4,
    "assessments/services.py": 5,
    "assessments/views.py": 4,
    "core/dashboard_selectors.py": 3,
    "notifications/services.py": 2,
    "parents/services.py": 4,
    "reports/services.py": 4,
    "scripts/seed_assessments.py": 2,
    "student_affairs/selectors.py": 2,
}


def _is_status(name: str | None) -> bool:
    return name is not None and (name == "status" or name.endswith("__status"))


def _is_literal(node: ast.AST) -> bool:
    return isinstance(node, ast.Constant) and node.value in LITERALS


def literal_sites(root: pathlib.Path = ROOT) -> Counter[str]:
    """ملفٌّ ← عددُ `status="pass"` و`x__status="fail"` و`r.status == "pass"` فيه."""
    found: Counter[str] = Counter()
    for path in sorted(root.rglob("*.py")):
        rel = path.relative_to(root)
        if rel.parts[0].startswith(".") or SKIPPED_PARTS & set(rel.parts):
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.keyword) and _is_status(node.arg) and _is_literal(node.value):
                found[rel.as_posix()] += 1
            elif (
                isinstance(node, ast.Compare)
                and isinstance(node.left, ast.Attribute)
                and _is_status(node.left.attr)
                and any(_is_literal(c) for c in node.comparators)
            ):
                found[rel.as_posix()] += 1
    return found


def has_single_definition(root: pathlib.Path = ROOT) -> bool:
    """هل عرّف `core/domain/grades.py` الحالاتِ الناجحةَ والراسبةَ باسمهما."""
    grades = root / "core" / "domain" / "grades.py"
    names = set()
    for node in ast.parse(grades.read_text(encoding="utf-8")).body:
        targets = node.targets if isinstance(node, ast.Assign) else []
        if isinstance(node, ast.AnnAssign):
            targets = [node.target]
        names.update(t.id for t in targets if isinstance(t, ast.Name))
    return {"PASSING_STATUSES", "FAILING_STATUSES"} <= names


def violations(root: pathlib.Path = ROOT) -> list[str]:
    allowed = {} if has_single_definition(root) else BEFORE_SINGLE_DEFINITION
    return [
        f"{path}: {count} موضعاً حرفيّاً (المسموح {allowed.get(path, 0)})"
        for path, count in sorted(literal_sites(root).items())
        if count > allowed.get(path, 0)
    ]


def test_pass_and_fail_are_read_through_the_single_definition():
    found = violations()
    assert not found, (
        "«ناجح/راسب» بنصٍّ حرفيّ — اقرأ `PASSING_STATUSES`/`FAILING_STATUSES` من "
        "`core.domain.grades` (المُرفَّعُ ناجح، والدورُ الثاني راسب). وإن جاء هذا بعد دمجٍ "
        "فالتعارضُ حُلّ بأخذ النصّ القديم في القارئ المنقول:\n  " + "\n  ".join(found)
    )


def test_the_scanner_sees_keywords_lookups_and_comparisons(tmp_path):
    (tmp_path / "core" / "domain").mkdir(parents=True)
    (tmp_path / "core" / "domain" / "grades.py").write_text("X = 1\n", encoding="utf-8")
    (tmp_path / "app").mkdir()
    (tmp_path / "app" / "selectors.py").write_text(
        "def f(qs, r):\n"
        "    qs.filter(status='pass')\n"
        "    Q(annual_results__status='fail')\n"
        "    qs.filter(status='open')\n"
        "    return r.status == 'pass'\n",
        encoding="utf-8",
    )
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_x.py").write_text("f(status='pass')\n", encoding="utf-8")
    assert literal_sites(tmp_path) == {"app/selectors.py": 3}
    assert violations(tmp_path) == ["app/selectors.py: 3 موضعاً حرفيّاً (المسموح 0)"]


def test_once_the_single_definition_exists_no_literal_is_allowed(tmp_path):
    (tmp_path / "core" / "domain").mkdir(parents=True)
    (tmp_path / "core" / "domain" / "grades.py").write_text(
        "PASSING_STATUSES: tuple[str, ...] = ('pass',)\nFAILING_STATUSES = ('fail',)\n",
        encoding="utf-8",
    )
    (tmp_path / "student_affairs").mkdir()
    (tmp_path / "student_affairs" / "selectors.py").write_text(
        "def f():\n    return Q(status='pass')\n", encoding="utf-8"
    )
    assert has_single_definition(tmp_path)
    assert violations(tmp_path) == ["student_affairs/selectors.py: 1 موضعاً حرفيّاً (المسموح 0)"]

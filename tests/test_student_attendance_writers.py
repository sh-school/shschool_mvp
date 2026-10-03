"""[LEGAL] حارسُ كتّاب `StudentAttendance` — لا كاتبَ جديدٌ يصل الرصدَ بلا قائمةٍ مسمّاة (W-20261002-020، M1).

الرصدُ المعتمَدُ سندُ خصمٍ وتأديب، وضمانةُ «المعتمَدُ وحدَه يصله» (قرارُ المالك D-125م) تسقط ما دام
أيُّ مسارٍ آخر يكتبه. فهذا الحارسُ يمسح الشيفرةَ (AST) ويُسقط كلَّ كاتبٍ على الجدول لم يُسجَّل هنا
**باسم دالّته وسببِه** — فمن أضاف كاتباً جديداً (خصوصاً يصله المعلّم) يقرأ هذا الملفَّ ويقرّر عن علمٍ.

ما يُعدّ كتابةً: `StudentAttendance.objects.<…>.create|update_or_create|get_or_create|bulk_create|
bulk_update|update|delete`، وبناءُ `StudentAttendance(...)`، وأيُّ `.save()`/`.update()`/`.delete()` على اسمٍ
في الدالّة نفسِها مشتقٍّ من استعلامٍ أو صفٍّ من `StudentAttendance` (تتبّعٌ بسيط). حدٌّ معلَنٌ: كتابةٌ بنموذجٍ
يُمرَّر ديناميكيّاً (`Model.objects…` في حلقة) أو بكائنٍ يُمرَّر بين دوالّ لا يلتقطها المسح — وتُسمَّى في
`UNDETECTABLE_BY_SCAN` بدليلٍ نصّيّ.

القائمةُ هي **الجردُ المراجَع** لكتّاب هذا الجدول يوم 2026-10-02 (راجعه 0105): لكلّ دالّةٍ سببُها
ومن يصلها. وإضافةُ سطرٍ هنا قرارٌ يُراجَع في الطلب لا إسكاتٌ للحارس.
"""

from __future__ import annotations

import ast
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent

WRITE_METHODS = {
    "create",
    "update_or_create",
    "get_or_create",
    "bulk_create",
    "bulk_update",
    "update",
    "delete",
}
SKIP_PARTS = {"tests", "migrations", "node_modules", ".venv", "venv", ".claude", "staticfiles"}

#: (الملفّ، الدالّة) ← لِمَ تكتب ومن يصلها. الدالّةُ `<module>` = كتابةٌ على مستوى الوحدة.
ALLOWED_WRITERS: dict[tuple[str, str], str] = {
    (
        "operations/services/attendance.py",
        "mark_attendance",
    ): "حالةُ الرصد من mark_single؛ المعلّمُ فيه محكومٌ بسياسة can_enter ولا يصل شُعبَ الجناح",
    (
        "operations/services/attendance.py",
        "bulk_mark_all_present",
    ): "«الكلُّ حاضر» من mark_all_present لمعلّم شعبةٍ بلا جناح أو مُسجِّل؛ لا يصله معلّمُ شعبة جناح",
    (
        "operations/period_register.py",
        "tap_late",
    ): "نقرةُ تأخّرِ المعلّم (source=teacher_late) تنتظر تثبيتَ المشرف — استثناءٌ مسمّىً بحكم 0105",
    (
        "operations/period_register.py",
        "confirm_period",
    ): "تثبيتُ المشرف/حاملِ الجناح للحصّة (source=supervisor) — لا يصله المعلّم",
    (
        "operations/exit_reflection.py",
        "_flip_unaccounted",
    ): "مهمّةُ Celery: قلبُ حاضرٍ إلى غائبٍ لخروجٍ لم يُحتسب (مشتقٌّ، AuditLog)",
    (
        "operations/exit_reflection.py",
        "revert_derived_absence",
    ): "إرجاعُ الغياب المشتقّ من خروجٍ عند العودة/الإلغاء (يصله معلّمُ الحصّة بقيده)",
    (
        "operations/undo.py",
        "undo_late_tap",
    ): "تراجعُ المعلّم عن نقرته وحدَها ما لم يثبّت المشرف (AuditLog)",
    (
        "operations/excuses.py",
        "grant_excuse",
    ): "وسمُ عذرٍ على غيابٍ قائم (حاملُ الجناح)",
    (
        "operations/excuses.py",
        "approve_excuse",
    ): "اعتمادُ عذرٍ بعد المهلة (النائب/المدير)",
    (
        "student_affairs/views.py",
        "tardiness_record",
    ): "تسجيلُ تأخّرٍ صباحيّ — شؤونُ الطلبة والمشرف، لا المعلّم",
    (
        "student_affairs/views.py",
        "tardiness_delete",
    ): "إلغاءُ تأخّرٍ صباحيّ — شؤونُ الطلبة والمشرف",
    (
        "core/management/commands/full_seed.py",
        "<seed>",
    ): "بذرٌ يدويّ بأمر management",
    (
        "scripts/seed_data.py",
        "<seed>",
    ): "بذرٌ يدويّ",
}

#: ملفّاتُ بذرٍ تُعدّ كتابتُها كلُّها («<seed>») لا بدالّة.
SEED_FILES = {"core/management/commands/full_seed.py", "scripts/seed_data.py"}


def _py_files():
    for path in ROOT.rglob("*.py"):
        parts = set(path.relative_to(ROOT).parts)
        if parts & SKIP_PARTS:
            continue
        if path.name in {"tests.py", "conftest.py"} or path.name.startswith("test_"):
            continue
        yield path


def _tainted_names(func: ast.AST) -> set[str]:
    """أسماءٌ في الدالّة تحمل استعلاماً أو صفّاً من `StudentAttendance` (تتبّعٌ بسيطٌ بمرحلتين)."""
    tainted: set[str] = set()
    for _ in range(2):
        for node in ast.walk(func):
            targets: list[ast.expr] = []
            value = None
            if isinstance(node, ast.Assign):
                targets, value = node.targets, node.value
            elif isinstance(node, (ast.AnnAssign, ast.NamedExpr)) and node.value is not None:
                targets, value = [node.target], node.value
            elif isinstance(node, ast.For):
                targets, value = [node.target], node.iter
            if value is None:
                continue
            text = ast.unparse(value)
            hit = "StudentAttendance" in text or any(name in text for name in tainted)
            if hit:
                for target in targets:
                    for leaf in ast.walk(target):
                        if isinstance(leaf, ast.Name):
                            tainted.add(leaf.id)
    return tainted


def _writes_in(tree: ast.AST) -> list[tuple[str, int]]:
    """كلُّ كتابةٍ على الجدول في الشجرة: (اسمُ الدالّة المحيطة، السطر)."""
    found: list[tuple[str, int]] = []

    class Visitor(ast.NodeVisitor):
        def __init__(self) -> None:
            self.stack: list[tuple[str, set[str]]] = []

        def _scope(self) -> str:
            return self.stack[-1][0] if self.stack else "<module>"

        def _tainted(self) -> set[str]:
            return self.stack[-1][1] if self.stack else set()

        def visit_FunctionDef(self, node):  # noqa: N802
            self.stack.append((node.name, _tainted_names(node)))
            self.generic_visit(node)
            self.stack.pop()

        visit_AsyncFunctionDef = visit_FunctionDef  # noqa: N815

        def visit_Call(self, node):  # noqa: N802
            func = node.func
            if isinstance(func, ast.Name) and func.id == "StudentAttendance":
                found.append((self._scope(), node.lineno))
            elif isinstance(func, ast.Attribute):
                receiver = ast.unparse(func.value)
                root = receiver.split(".")[0].split("(")[0].split("[")[0]
                if "StudentAttendance" in receiver and func.attr in WRITE_METHODS:
                    found.append((self._scope(), node.lineno))
                elif root in self._tainted() and func.attr in WRITE_METHODS | {"save"}:
                    found.append((self._scope(), node.lineno))
            self.generic_visit(node)

    Visitor().visit(tree)
    return found


def _scan() -> dict[tuple[str, str], list[int]]:
    result: dict[tuple[str, str], list[int]] = {}
    for path in _py_files():
        source = path.read_text(encoding="utf-8")
        if "StudentAttendance" not in source:
            continue
        try:
            tree = ast.parse(source)
        except SyntaxError:
            continue
        rel = path.relative_to(ROOT).as_posix()
        for scope, line in _writes_in(tree):
            if rel in SEED_FILES:
                scope = "<seed>"
            result.setdefault((rel, scope), []).append(line)
    return result


def test_no_unlisted_writer_of_student_attendance():
    """كاتبٌ على StudentAttendance خارج القائمة المسمّاة يُسقط الحارس."""
    unlisted = {key: lines for key, lines in _scan().items() if key not in ALLOWED_WRITERS}
    assert not unlisted, (
        "كتّابٌ جدد على StudentAttendance لم يُراجَعوا — أضفهم إلى ALLOWED_WRITERS بسببٍ يُراجَع في الطلب "
        "(وإن كان يصلهم المعلّمُ فمرِّرهم بـoperations/attendance_policy.can_enter):\n"
        + "\n".join(
            f"  {file}::{scope} (السطور {lines})" for (file, scope), lines in unlisted.items()
        )
    )


def test_every_listed_writer_still_exists():
    """سطرٌ في القائمة لا كاتبَ وراءه = قائمةٌ تتقادم — يُحذف."""
    seen = set(_scan())
    stale = sorted(key for key in ALLOWED_WRITERS if key not in seen)
    assert not stale, f"مدخلاتٌ في ALLOWED_WRITERS بلا كاتبٍ فعليّ: {stale}"


#: كتّابٌ لا يلتقطهم المسح (نموذجٌ يُمرَّر ديناميكيّاً، أو كائنٌ يصل من المستدعي، أو علاقةٌ عكسيّة) —
#: يُتحقَّق منهم بدليلٍ نصّيّ في الملفّ بدل المسح، وسببُ كلٍّ منهم هنا.
UNDETECTABLE_BY_SCAN: dict[tuple[str, str], str] = {
    (
        "governance/erasure_service.py",
        '(StudentAttendance, "student", False)',
    ): "محوُ طالبٍ (PDPPL م.18): حذفٌ مشروعٌ يمرّ بقائمة نماذج المحو",
    (
        "operations/excuses.py",
        'excuse.rows.update(excuse=None, excuse_type="")',
    ): "revoke_excuse: سحبُ عذرٍ عبر العلاقة العكسيّة rows (حاملُ الجناح)",
    (
        "operations/undo.py",
        "    row.delete()",
    ): "delete_attendance_event: حذفُ حاملِ الجناح لحدثٍ بسببٍ إلزاميّ (AuditLog)",
}


def test_undetectable_writers_are_still_where_we_say():
    for (rel, needle), _why in UNDETECTABLE_BY_SCAN.items():
        text = (ROOT / rel).read_text(encoding="utf-8")
        assert needle in text, f"{rel}: لم يعد فيه {needle!r} — حدِّث الجرد"

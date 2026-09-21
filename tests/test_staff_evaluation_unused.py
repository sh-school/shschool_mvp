"""[GUARD] `operations.StaffEvaluation` حُذف (هجرة `operations/0056`): لا يُعاد استعمالُه ولا إدخالُه.

ADR-0002 (`docs/adr/0002-unified-staff-appraisal.md` §1.3، §5): تقييمُ الأداء في
`quality.EmployeeEvaluation`، والنموذجُ القديم صفرٌ في الإنتاج. وحذفُ جدولٍ يكون على خطوتين
في إصدارين (CLAUDE.md، «توسيعٌ ثمّ تقليص»): هذا الحارسُ يضمن أنّ الشيفرةَ التي تعمل أثناء
النشر لا تلمس الجدولَ (كان ذلك شرطَ هجرة الحذف)؛ وبعدها يمنع إعادةَ النموذج أو استعمالِ علاقاته العكسيّة.
"""

from __future__ import annotations

import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parent.parent

#: استعمالٌ لا ذكر: استيرادٌ (سطراً أو بين قوسين)، أو `StaffEvaluation.` / `StaffEvaluation(`،
#: أو علاقةٌ عكسيّة. فتعليقٌ أو وصفٌ يسمّي النموذجَ المُهمَل لا يُسقط الحارس.
PATTERN = re.compile(
    r"import[^\n]*\bStaffEvaluation\b"
    r"|^\s*StaffEvaluation,?\s*$"
    r"|\bStaffEvaluation\s*[.(]"
    r"|\bstaff_evaluations\b|\bevaluations_as_staff\b|\bevaluations_as_evaluator\b"
)

#: ما يجوز أن يذكره: سجلُّ التدقيق يسمّيه نوعَ كيان (نصٌّ لا استعمال، وسجلّاتٌ قديمةٌ قد تحمله)،
#: والهجراتُ (تاريخٌ لا شيفرة)، وهذا الحارسُ.
ALLOWED = {
    "core/models/audit.py",
    "tests/test_staff_evaluation_unused.py",
}
SKIP_DIRS = {".git", ".claude", "node_modules", "migrations", "staticfiles", "__pycache__", "docs"}


def _python_and_template_files():
    for path in ROOT.rglob("*"):
        if path.suffix not in {".py", ".html"} or not path.is_file():
            continue
        if SKIP_DIRS & set(path.relative_to(ROOT).parts):
            continue
        yield path


def test_nothing_reads_or_writes_the_deprecated_staff_evaluation():
    offenders = [
        f"{path.relative_to(ROOT).as_posix()}:{n}"
        for path in _python_and_template_files()
        if path.relative_to(ROOT).as_posix() not in ALLOWED
        for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1)
        if PATTERN.search(line)
    ]
    assert not offenders, (
        "استعمالٌ لـ`operations.StaffEvaluation` المُهمَل — استعمل `quality.EmployeeEvaluation` "
        "(ADR-0002):\n  " + "\n  ".join(offenders)
    )


def test_the_guard_pattern_catches_usage_but_not_prose():
    for usage in (
        "from operations.models import StaffEvaluation, TeacherAbsence",
        "    StaffEvaluation,",
        "rows = StaffEvaluation.objects.filter(school=school)",
        "school.staff_evaluations.filter(staff=user)",
        "user.evaluations_as_staff.count()",
    ):
        assert PATTERN.search(usage), usage
    for prose in (
        "# StaffEvaluation المُهمَل: لا قارئَ ولا كاتب",
        "وتقييمُ الأداء في `quality.EmployeeEvaluation` لا في `StaffEvaluation` المُهمَل.",
    ):
        assert not PATTERN.search(prose), prose

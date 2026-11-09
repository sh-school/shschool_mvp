"""حارسُ عقد التصدير (W-20261109-012): كلُّ قالبٍ فيه `export_button` إمّا نوعُه مسجَّلٌ في السجلّ المركزيّ أو مستثنًى بسببٍ مكتوب.

سقّاطةٌ تنقص ولا تزيد: ترحيلُ صفحةٍ إلى العقد (بطاقاتٌ لاحقة) ينقل قالبَها من `EXEMPT` إلى `REGISTERED`؛
وقالبٌ جديدٌ فيه زرُّ تصديرٍ بلا بندٍ هنا يُفشل الحارس فيُدفع إلى السجلّ بدل ملفٍّ يخرج بلا عقد.
"""

import re
from pathlib import Path

from core.exports import registry

ROOT = Path(__file__).resolve().parent.parent
BUTTON = re.compile(r"\{%-?\s*export_button\b")

#: قالبٌ ← أنواعُ السجلّ التي يخرج بها (كلُّها مسجَّلةٌ حقّاً).
REGISTERED = {
    "templates/student_affairs/student_list.html": {
        "student_affairs.students_xlsx",
        "student_affairs.students_pdf",
    },
}

_LATER = (
    "مسارُه متزامنٌ أو غيرُ مسجَّل بعدُ — يُرحَّل إلى عقد core/exports في بطاقةٍ لاحقة (حدودُ W-20261109-012)"
)
_NOT_A_TABLE = "ليس جدولَ قائمةٍ بفلتر: وثيقةٌ مفردةٌ أو تقريرٌ ثابت — لا مرشِّحَ يُحفظ في الملفّ"

#: قالبٌ ← سببُ الاستثناء المكتوب.
EXEMPT = {
    "templates/academic_management/reports/_base.html": _LATER,
    "templates/analytics/kpi_dashboard.html": _NOT_A_TABLE,
    "templates/assessments/class_gradebook.html": _LATER,
    "templates/behavior/daily_report.html": _LATER,
    "templates/behavior/dashboard.html": _LATER,
    "templates/behavior/statistics.html": _LATER,
    "templates/behavior/student_profile.html": _NOT_A_TABLE,
    "templates/breach/detail.html": _NOT_A_TABLE,
    "templates/core/student_import_export.html": _LATER,
    "templates/operations/absence_followup/base.html": _LATER,
    "templates/operations/absence_followup/viewer.html": _LATER,
    "templates/parents/dashboard.html": _NOT_A_TABLE,
    "templates/quality/observation_detail.html": _NOT_A_TABLE,
    "templates/quality/observation_list.html": _LATER,
    "templates/quality/observation_pdf_view.html": _NOT_A_TABLE,
    "templates/quality/progress_report.html": _NOT_A_TABLE,
    "templates/reports/index.html": _LATER,
    "templates/reports/report_viewer.html": _LATER,
    "templates/schedule/pages_view.html": _NOT_A_TABLE,
    "templates/schedule/print_view.html": _NOT_A_TABLE,
    "templates/staff_affairs/attendance_board.html": _LATER,
    "templates/staff_affairs/attendance_report.html": _LATER,
    "templates/staging/import_grades.html": _NOT_A_TABLE,
    "templates/student_affairs/activity_list.html": _LATER,
    "templates/student_affairs/attendance_overview.html": _LATER,
    "templates/student_affairs/behavior_overview.html": _LATER,
    "templates/student_affairs/movements.html": _LATER,
    "templates/student_affairs/student_profile.html": _NOT_A_TABLE,
    "templates/student_affairs/tardiness_list.html": _LATER,
    "templates/wings/exit_permits.html": _LATER,
    "templates/wings/ministry_report.html": _LATER,
    "templates/wings/partials/record_panel.html": _LATER,
}


def _templates_with_buttons() -> set[str]:
    found = set()
    for path in (ROOT / "templates").rglob("*.html"):
        if BUTTON.search(path.read_text(encoding="utf-8")):
            found.add(path.relative_to(ROOT).as_posix())
    return found


def test_every_export_button_template_is_registered_or_exempt_with_a_reason():
    found = _templates_with_buttons()

    unknown = found - set(REGISTERED) - set(EXEMPT)

    assert not unknown, (
        "قالبٌ فيه export_button بلا نوعٍ مسجَّل ولا استثناءٍ مكتوب — سجِّل نوعَه في core.exports.registry "
        f"أو أضفه إلى EXEMPT بسببٍ: {sorted(unknown)}"
    )


def test_the_lists_hold_no_dead_or_double_entries():
    found = _templates_with_buttons()

    assert not (set(REGISTERED) & set(EXEMPT)), "قالبٌ في القائمتين"
    assert not ((set(REGISTERED) | set(EXEMPT)) - found), "بندٌ بلا قالبٍ فيه export_button"
    assert all(reason.strip() for reason in EXEMPT.values()), "استثناءٌ بلا سبب"


def test_every_registered_template_kind_exists_in_the_registry():
    missing = {k for kinds in REGISTERED.values() for k in kinds if registry.get(k) is None}

    assert not missing, f"نوعٌ مذكورٌ هنا وغيرُ مسجَّل: {sorted(missing)}"

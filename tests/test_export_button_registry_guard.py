"""حارس عقد التصدير المركزيّ (W-20261109-001): كلُّ `export_button` إمّا نوعٌ مسجَّلٌ في السجلّ المركزيّ أو مستثنًى بسببٍ مكتوب.

النوعُ المسجَّل يُعلَن في الوسم بـ`job="<kind>"` (`data-export-job`) ويجب أن يكون في `core.exports.registry`.
والقوالبُ التي لم تُرحَّل بعدُ مدرجةٌ في `EXCLUDED` بسببها؛ ويُحذف القالبُ منها عند ترحيله (يفشل الاختبارُ إن بقي بلا حاجة)،
فالقائمةُ لا تنمو بصمت: قالبٌ جديدٌ بزرٍّ غير مسجَّل يُرفض.
"""

import pathlib
import re

from core.exports import registry

ROOT = pathlib.Path(__file__).resolve().parent.parent
TEMPLATES = ROOT / "templates"
TAG = re.compile(r"\{%\s*export_button\b(.*?)%\}", re.DOTALL)
JOB = re.compile(r"""\bjob\s*=\s*["']([^"']+)["']""")

_LEGACY = "مسارٌ متزامنٌ قديم خارج السجلّ المركزيّ — يُرحَّل في بطاقة ترحيل صفحاته"
#: قالبٌ ← سببُ استثنائه من التسجيل.
EXCLUDED: dict[str, str] = {
    "analytics/kpi_dashboard.html": _LEGACY + " (التحليلات)",
    "core/student_import_export.html": _LEGACY + " (استيراد الطلاب وتصديرهم)",
    "reports/report_viewer.html": _LEGACY + " (التقارير)",
    "reports/index.html": _LEGACY + " (التقارير)",
    "parents/dashboard.html": _LEGACY + " (أولياء الأمور)",
    "schedule/print_view.html": "job باسمٍ مختصرٍ قديم (pdf/excel) لا نوعٍ مسجَّل — يُرحَّل مع الجدول",
    "assessments/class_gradebook.html": _LEGACY + " (سجلّ الدرجات)",
    "wings/exit_permits.html": _LEGACY + " (الأجنحة)",
    "wings/ministry_report.html": _LEGACY + " (الأجنحة)",
    "operations/absence_followup/base.html": _LEGACY + " (متابعة الغياب)",
    "academic_management/reports/_base.html": _LEGACY + " (الأكاديمي)",
    "schedule/pages_view.html": _LEGACY + " (الجدول)",
    "behavior/daily_report.html": _LEGACY + " (السلوك)",
    "behavior/dashboard.html": _LEGACY + " (السلوك)",
    "wings/partials/record_panel.html": _LEGACY + " (الأجنحة)",
    "breach/detail.html": _LEGACY + " (الانتهاكات)",
    "staging/import_grades.html": _LEGACY + " (استيراد الدرجات)",
    "behavior/student_profile.html": _LEGACY + " (السلوك)",
    "behavior/statistics.html": _LEGACY + " (السلوك)",
    "student_affairs/activity_list.html": _LEGACY + " (الأنشطة)",
    "quality/observation_detail.html": _LEGACY + " (الجودة)",
    "staff_affairs/attendance_board.html": _LEGACY + " (شؤون الموظفين)",
    "quality/observation_list.html": _LEGACY + " (الجودة)",
    "quality/observation_pdf_view.html": _LEGACY + " (الجودة)",
    "staff_affairs/attendance_report.html": _LEGACY + " (شؤون الموظفين)",
    "quality/progress_report.html": _LEGACY + " (الجودة)",
    "student_affairs/attendance_overview.html": _LEGACY + " (الحضور)",
    "student_affairs/behavior_overview.html": _LEGACY + " (السلوك)",
    "operations/absence_followup/viewer.html": _LEGACY + " (متابعة الغياب)",
    "student_affairs/movements.html": "النوعُ movements_xlsx مسجَّلٌ لكنّ الزرَّ لم يُربط به بـjob — يُربط في بطاقة الترحيل",
    "student_affairs/student_list.html": "النوعُ students_pdf مسجَّلٌ لكنّ الزرَّ لم يُربط به بـjob — يُربط في بطاقة سجلّ الطلاب",
    "student_affairs/student_profile.html": _LEGACY + " (ملفّ الطالب)",
    "student_affairs/tardiness_list.html": _LEGACY + " (التأخّر)",
}


def unregistered_buttons(src: str) -> list[str]:
    """وسومُ `export_button` في نصّ قالبٍ لا يحمل `job` لنوعٍ مسجَّل (و«طباعة» لا تُسجَّل: لا ملفَّ يُبنى)."""
    bad = []
    for match in TAG.finditer(src):
        args = match.group(1)
        if re.match(r"""\s*["']print["']""", args):
            continue
        job = JOB.search(args)
        if job is None or job.group(1) not in registry.kinds():
            bad.append(" ".join(args.split()))
    return bad


def _templates_with_buttons() -> dict[str, str]:
    found = {}
    for path in TEMPLATES.rglob("*.html"):
        src = path.read_text(encoding="utf-8")
        if "export_button" in src:
            found[path.relative_to(TEMPLATES).as_posix()] = src
    return found


def test_every_export_button_is_registered_or_excluded_with_a_reason():
    unlisted = {
        rel: bad
        for rel, src in _templates_with_buttons().items()
        if rel not in EXCLUDED and (bad := unregistered_buttons(src))
    }
    assert not unlisted, (
        'زرُّ تصديرٍ لا نوعَ مسجَّلاً له (`job="<kind>"` من core.exports.registry) ولا استثناءَ مكتوباً في '
        f"EXCLUDED: {unlisted}"
    )


def test_every_exclusion_has_a_reason_and_is_still_needed():
    buttons = _templates_with_buttons()
    empty = [rel for rel, why in EXCLUDED.items() if not why.strip()]
    stale = [
        rel for rel in EXCLUDED if rel not in buttons or not unregistered_buttons(buttons[rel])
    ]
    assert not empty, f"استثناءٌ بلا سببٍ مكتوب: {empty}"
    assert not stale, f"استثناءٌ لم يعد لازماً (القالبُ رُحِّل أو حُذف) — احذفه من EXCLUDED: {stale}"


def test_a_registered_job_kind_passes_and_an_unregistered_one_fails():
    sample = '{% export_button "pdf" "x:y" job="tests.guard_probe" %}?a=1{% endexport_button %}'
    registry.register("tests.guard_probe", build=lambda s, u, p: None, capability="x")  # type: ignore[arg-type,return-value]
    try:
        assert unregistered_buttons(sample) == []
    finally:
        registry.unregister("tests.guard_probe")
    assert unregistered_buttons(sample) != []
    assert unregistered_buttons('{% export_button "pdf" "x:y" %}{% endexport_button %}') != []
    assert unregistered_buttons('{% export_button "print" %}{% endexport_button %}') == []

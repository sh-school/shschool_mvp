"""حرّاسُ التصدير المركزيّ (VI-30ب): سقّاطاتٌ تنقص ولا تزيد — كلُّ تصديرٍ جديدٍ يمرّ بالسجلّ لا بمسار الطلب.

* كلُّ `log_export(kind)` له بنّاءٌ مسجَّلٌ في `core.exports.registry` **أو** بندٌ في `SYNC_ONLY_*` أدناه (قائمةٌ مؤقّتةٌ
  تنقص بتحويل نوعٍ إلى مهمّةٍ خلفيّة، فيُحذف بندُه هنا في الطلب نفسِه — وبندٌ بلا أصلٍ في الشيفرة أو مسجَّلٌ يُفشل الحارس).
* لا مُصدِّرَ ثقيلاً (`render_pdf`/`render_pdf_bytes`/`Workbook`) جديداً داخل دالّةِ عرض: `HEAVY_IN_VIEWS` تنقص ولا تزيد.
  (نداءٌ عبر دالّةٍ مساعدةٍ لا يُلتقط — سقّاطةٌ لا برهان.)
* الافتراضُ الآمن: نوعٌ جديدٌ يُكتب `log_export(kind)` بلا بنّاءٍ مسجَّل يسقط هنا فيُدفع إلى السجلّ (مهمّةٌ خلفيّة) لا يبقى متزامناً صامتاً.
"""

from core.exports import registry
from tests import export_scan

#: أنواعٌ متزامنةٌ اليوم (قياس 2026-09-26: بعضُها 400–8300ms) — تُحوَّل واحداً بعد آخر بالأبطأ فالأبطأ.
SYNC_ONLY_KINDS = frozenset(
    {
        "analytics.kpi_monthly_pdf",
        "assessments.gradebook_xlsx",
        "breach.report_pdf",
        "core.students_import_template_xlsx",
        "core.students_xlsx",
        "exam_control.incident_pdf",
        "exam_control.session_report_pdf",
        "quality.observation_pdf",
        "quality.progress_report_pdf",
        "reports.attendance",
        "reports.attendance_xlsx",
        "reports.behavior_xlsx",
        "reports.certificate",
        "reports.class_certificates",
        "reports.class_results",
        "reports.class_results_xlsx",
        "reports.student_annual_result",
        "reports.student_result",
        "staff_affairs.attendance_month_xlsx",
        "staging.grade_template_xlsx",
        "student_affairs.activities_xlsx",
        "student_affairs.attendance_overview_pdf",
        "student_affairs.attendance_xlsx",
        "student_affairs.behavior_overview_pdf",
        "student_affairs.behavior_xlsx",
        "student_affairs.student_profile_pdf",
        "student_affairs.students_pdf",
        "student_affairs.students_xlsx",
        "student_affairs.tardiness_pdf",
        "student_affairs.tardiness_xlsx",
    }
)

#: بادئاتُ أنواعٍ ديناميكيّة (f-string) متزامنةٌ اليوم.
SYNC_ONLY_PREFIXES = frozenset({"academic.", "wings.register_"})

#: دوالُّ عرضٍ تنادي مُصدِّراً ثقيلاً مباشرةً اليوم — تنقص بتحويلها إلى بنّاءٍ مسجَّل.
HEAVY_IN_VIEWS = frozenset(
    {
        "academic_management/views.py::_export_response",
        "analytics/views.py::kpi_monthly_pdf",
        "assessments/views.py::export_gradebook",
        "behavior/views.py::_render_behavior_pdf",
        "breach/views.py::breach_pdf",
        "core/views_students.py::_setup_workbook",
        "core/views_students.py::student_export_excel",
        "core/views_students.py::student_import_template",
        "exam_control/views.py::incident_pdf",
        "exam_control/views.py::session_report_pdf",
        "quality/observation_views.py::observation_pdf",
        "quality/views_reports.py::progress_report_pdf",
        "reports/views.py::attendance_report_pdf",
        "reports/views.py::class_certificates_pdf",
        "reports/views.py::class_results_pdf",
        "reports/views.py::student_annual_result_pdf",
        "reports/views.py::student_certificate_pdf",
        "reports/views.py::student_result_pdf",
        "staging/views.py::download_grade_template",
        "student_affairs/views.py::activities_export_excel",
        "student_affairs/views.py::attendance_export_excel",
        "student_affairs/views.py::attendance_overview_pdf",
        "student_affairs/views.py::behavior_export_excel",
        "student_affairs/views.py::behavior_overview_pdf",
        "student_affairs/views.py::student_export_excel",
        "student_affairs/views.py::student_list_pdf",
        "student_affairs/views.py::student_profile_pdf",
        "student_affairs/views.py::tardiness_export_excel",
        "student_affairs/views.py::tardiness_pdf",
        "wings/views_register.py::_respond",
    }
)


def test_every_logged_export_kind_has_a_builder_or_is_listed():
    literal, prefixes = export_scan.log_export_kinds()

    unregistered = {k: f for k, f in literal.items() if k not in registry.kinds()}
    new = {k: f for k, f in unregistered.items() if k not in SYNC_ONLY_KINDS}
    new_prefixes = {p: f for p, f in prefixes.items() if p not in SYNC_ONLY_PREFIXES}

    assert not new and not new_prefixes, (
        "تصديرٌ جديدٌ بلا بنّاءٍ في سجلّ التصدير المركزيّ (core.exports.registry) — سجِّله (مهمّةٌ خلفيّةٌ افتراضاً؛ "
        f"والمتزامنُ بقياسِ p95 مثبَّت) بدل مسارٍ متزامنٍ صامت: {new} {new_prefixes}"
    )


def test_the_sync_only_list_only_shrinks():
    """نوعٌ حُوِّل إلى بنّاءٍ أو حُذف من الشيفرة يخرج من القائمة — فلا تبقى بنودٌ ميّتةٌ تُخفي رجوعَه."""
    literal, prefixes = export_scan.log_export_kinds()

    stale = {k for k in SYNC_ONLY_KINDS if k not in literal}
    converted = {k for k in SYNC_ONLY_KINDS if k in registry.kinds()}
    stale_prefixes = {p for p in SYNC_ONLY_PREFIXES if p not in prefixes}

    assert (
        not stale and not converted and not stale_prefixes
    ), f"احذف من SYNC_ONLY: ميّتٌ {sorted(stale | stale_prefixes)} · مسجَّلٌ {sorted(converted)}"


def test_no_new_heavy_exporter_in_a_request_path():
    found = export_scan.heavy_calls_in_views()

    added = found - HEAVY_IN_VIEWS
    removed = HEAVY_IN_VIEWS - found

    assert not added, f"مُصدِّرٌ ثقيلٌ جديدٌ في مسار الطلب — اجعله بنّاءً في سجلّ التصدير: {sorted(added)}"
    assert not removed, f"حُوِّلت — احذفها من HEAVY_IN_VIEWS: {sorted(removed)}"

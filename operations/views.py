"""
operations/views.py — Thin façade
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
يستورد من الملفات المقسّمة ويُعيد تصديرها للحفاظ على توافق urls.py.

الملفات الحقيقية:
  views_attendance.py — الحضور والحصص اليومية (7 دوال)
  views_schedule.py   — الجداول والبدلاء والجدولة الذكية (12 دالة)
  views_swap.py       — التبديل والتعويض والحصص الحرة (11 دالة)
"""

# ── Attendance ──────────────────────────────────────────────────
from .views_attendance import (
    attendance_view,
    cancel_exit_view,
    complete_session,
    daily_report,
    mark_all_present,
    mark_exit,
    mark_late_tap,
    mark_return,
    mark_single,
    schedule,
    session_summary,
    undo_late_tap_view,
)

# ── Schedule & Substitute ───────────────────────────────────────
from .views_schedule import (
    absence_detail,
    add_exemption,
    assign_substitute,
    exemption_grid,
    export_job_status,
    register_teacher_absence,
    remove_exemption,
    remove_exemptions,
    remove_preferences,
    save_subject_scheduling,
    schedule_export_excel,
    schedule_export_pdf,
    schedule_pages,
    schedule_pages_paper,
    schedule_pages_pdf,
    schedule_print,
    schedule_print_view,
    schedule_quality_lab,
    schedule_settings,
    smart_generate,
    smart_generate_status,
    smart_schedule_view,
    substitute_report,
    teacher_absence_list,
    teacher_load_report,
    teacher_preferences,
    weekly_schedule,
)
from .views_schedule_drafts import approve_schedule

# ── Swap & Compensatory ─────────────────────────────────────────
from .views_swap import (
    absence_swap_create,
    absence_swap_options,
    build_free_slots,
    compensatory_approve,
    compensatory_list,
    compensatory_request,
    swap_approve,
    swap_cancel,
    swap_list,
    swap_options_htmx,
    swap_request,
    swap_respond,
    teacher_free_slots,
    teacher_weekly_view,
)

__all__ = [
    # attendance
    "schedule",
    "attendance_view",
    "mark_single",
    "mark_all_present",
    "complete_session",
    "session_summary",
    "daily_report",
    "mark_late_tap",
    "mark_exit",
    "mark_return",
    "undo_late_tap_view",
    "cancel_exit_view",
    # schedule
    "weekly_schedule",
    "schedule_export_excel",
    "schedule_export_pdf",
    "schedule_print",
    "schedule_print_view",
    "schedule_pages",
    "schedule_pages_paper",
    "schedule_pages_pdf",
    "teacher_absence_list",
    "register_teacher_absence",
    "absence_detail",
    "assign_substitute",
    "substitute_report",
    "smart_schedule_view",
    "schedule_quality_lab",
    "smart_generate",
    "smart_generate_status",
    "approve_schedule",
    "teacher_load_report",
    "schedule_settings",
    "save_subject_scheduling",
    "add_exemption",
    "exemption_grid",
    "export_job_status",
    "remove_exemption",
    "remove_exemptions",
    "remove_preferences",
    "teacher_preferences",
    # swap
    "absence_swap_options",
    "absence_swap_create",
    "swap_list",
    "swap_request",
    "swap_options_htmx",
    "swap_respond",
    "swap_approve",
    "swap_cancel",
    "compensatory_list",
    "compensatory_request",
    "compensatory_approve",
    "teacher_free_slots",
    "build_free_slots",
    "teacher_weekly_view",
]

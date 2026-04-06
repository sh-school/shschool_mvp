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
    complete_session,
    daily_report,
    mark_all_present,
    mark_single,
    schedule,
    session_summary,
)

# ── Schedule & Substitute ───────────────────────────────────────
from .views_schedule import (
    absence_detail,
    add_exemption,
    approve_schedule,
    assign_substitute,
    generate_sessions,
    register_teacher_absence,
    remove_exemption,
    schedule_print,
    schedule_settings,
    schedule_slot_create,
    schedule_slot_delete,
    smart_generate,
    smart_schedule_view,
    substitute_report,
    teacher_absence_list,
    teacher_load_report,
    teacher_preferences,
    toggle_double_period,
    weekly_schedule,
)

# ── Swap & Compensatory ─────────────────────────────────────────
from .views_swap import (
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
    # schedule
    "weekly_schedule",
    "schedule_print",
    "schedule_slot_create",
    "schedule_slot_delete",
    "generate_sessions",
    "teacher_absence_list",
    "register_teacher_absence",
    "absence_detail",
    "assign_substitute",
    "substitute_report",
    "smart_schedule_view",
    "smart_generate",
    "approve_schedule",
    "teacher_load_report",
    "schedule_settings",
    "add_exemption",
    "remove_exemption",
    "toggle_double_period",
    "teacher_preferences",
    # swap
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

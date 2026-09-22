"""ما تعرضه لوحةُ التحكم الرئيسيّة: عناوينُ الأرقام وألوانُها وروابطُها.

كانت هذه الأحكامُ شروطاً في قالبٍ من ألف سطر: «↑ 3% عن أمس» تُركَّب بثلاثة
فروع، ولونُ المخالفات يُحكم في موضع، وسطرُ «تنبيه» تحت الرقم يكرّر حكمَه في
موضعٍ آخر. فالقالبُ الآن يسمّي، وهذه الوحدةُ تحكم — مرّةً واحدة، ومختبَرةً.

والقاعدةُ في اللون: الرقمُ الذي يطلب فعلاً (تبديلٌ ينتظر، طالبٌ أُرسل للمنزل)
يُلوَّن بحاله، والرقمُ الصفريّ أخضر. فلا حاجةَ لسطر «مراجعة» تحته.
"""

from __future__ import annotations

from django.urls import reverse

#: شارةُ حالة الحصّة في لوحة المعالج — كانت `badge-status {{ s.status }}` بلا
#: تعريفٍ في CSS فتُكتب الحالةُ نصّاً عارياً بلا لون.
SESSION_STATUS_BADGE = {
    "scheduled": "status-info",
    "in_progress": "status-warning",
    "completed": "status-success",
    "cancelled": "status-gray",
}


def _delta(value, unit: str = "") -> str:
    """«↑ 3% عن أمس» — والصفرُ «= كأمس»، والمجهولُ فراغ."""
    if value is None:
        return ""
    if value == 0:
        return "= كأمس"
    arrow = "↑" if value > 0 else "↓"
    return f"{arrow} {abs(value)}{unit} عن أمس"


def _pending(count, tone: str = "amber") -> str:
    return tone if count else "green"


def chunk_for_grid(items: list, columns: int) -> list[list]:
    """يقسم قائمةً طويلةً إلى أعمدةٍ متجاورة — تُعرض داخل `.auto-grid` في القالب.

    بطاقةٌ فيها قائمةٌ قصيرةُ السطر (اسمٌ ورقم) وصفوفُها عشرات كانت تُرسم
    عموداً واحداً طويلاً بعرض الصفحة كاملها وباقي عرضها فارغ. التقسيمُ
    متتابعٌ لا تبادليّ: أوّلُ عمودٍ يحمل رأسَ القائمة ثم يليه العمود الثاني.
    """
    if not items:
        return []
    size = -(-len(items) // columns) or 1  # ceil division
    return [items[i : i + size] for i in range(0, len(items), size)]


def present(ctx: dict) -> dict:
    """المفاتيحُ التي يقرؤها قالبُ الدور — تُضاف فوق سياق العرض."""
    kind = ctx.get("view_type")
    school = ctx.get("school")
    today = ctx.get("today")
    day = f"{today:%d/%m/%Y}" if today else ""
    out = {"subtitle": " · ".join(p for p in (getattr(school, "name", ""), day) if p)}

    if kind == "director":
        critical = ctx.get("behavior_critical") or 0
        sent_home = ctx.get("clinic_sent_home") or 0
        out.update(
            attendance_label=f"{ctx.get('attendance_pct', 0)}%",
            att_delta_label=_delta(ctx.get("att_delta"), "%"),
            absent_delta_label=_delta(ctx.get("absent_delta")),
            sessions_sub=f"{ctx.get('completed', 0)} مكتملة · {ctx.get('in_progress', 0)} جارية",
            behavior_sub=f"{critical} حرجة" if critical else "",
            behavior_tone="red" if critical else "maroon",
            behavior_url=reverse("behavior:dashboard"),
            clinic_sub=f"{sent_home} أُرسلوا للمنزل" if sent_home else "",
            clinic_tone="red" if sent_home else "blue",
            clinic_url=reverse("clinic:dashboard"),
            library_tone=_pending(ctx.get("library_overdue"), "purple"),
            library_url=reverse("library:dashboard"),
            swaps_tone=_pending(ctx.get("pending_swaps"), "orange"),
            swaps_url=reverse("swap_list"),
            comp_tone=_pending(ctx.get("pending_comp"), "teal"),
            comp_url=reverse("compensatory_list"),
            teachers_tone=_pending(ctx.get("absent_teachers_today"), "red"),
            teachers_url=reverse("absence_list"),
            pass_label=f"{ctx.get('pass_pct', 0)}%",
            failing_tone=_pending(ctx.get("failing_count"), "red"),
            failing_url=reverse("failing_students"),
        )
    elif kind in ("teacher", "coordinator"):
        out.update(
            swaps_url=reverse("swap_list"),
            coord_swaps_tone=_pending(ctx.get("coord_pending_swaps"), "orange"),
            coord_comp_tone=_pending(ctx.get("coord_pending_comp"), "teal"),
            coord_absent_tone=_pending(ctx.get("coord_absent_today"), "red"),
            comp_url=reverse("compensatory_list"),
            absence_url=reverse("absence_list"),
            my_swaps_label=f"{ctx.get('my_pending_swaps')} طلب تبديل ينتظر ردّك",
        )
    elif kind == "student":
        out.update(
            student_att_label=f"{ctx.get('student_att_pct', 0)}%",
            student_failed_tone=_pending(ctx.get("student_failed"), "red"),
            student_failed_sub=f"من {ctx.get('student_subjects_total', 0)} مادّة",
        )
    elif kind == "specialist_social":
        critical = ctx.get("behavior_critical") or 0
        out.update(
            chronic_tone=_pending(ctx.get("chronic_absent"), "red"),
            behavior_sub=f"{critical} خطرة" if critical else "",
            behavior_tone="red" if critical else "maroon",
            failing_tone=_pending(ctx.get("failing_students"), "orange"),
        )
    elif kind == "therapist":
        out.update(
            sessions_sub=f"{ctx.get('completed_sessions_today', 0)} مكتملة",
            week_label=f"{ctx.get('week_completed', 0)}/{ctx.get('week_total', 0)}",
            session_status_badges=SESSION_STATUS_BADGE,
        )
    elif kind == "activities":
        out.update(activities_sub=f"من {ctx.get('activities_total', 0)} هذا العام")
    elif kind == "admin_ops":
        out.update(
            teachers_tone=_pending(ctx.get("absent_teachers_today"), "red"),
            swaps_tone=_pending(ctx.get("pending_swaps"), "orange"),
            comp_tone=_pending(ctx.get("pending_comp"), "teal"),
        )
    elif kind == "service":
        sent_home = ctx.get("clinic_sent_home") or 0
        out.update(
            clinic_sub=f"{sent_home} أُرسلوا للمنزل" if sent_home else "",
            clinic_tone="red" if sent_home else "green",
            library_tone=_pending(ctx.get("library_overdue"), "red"),
        )
    return out

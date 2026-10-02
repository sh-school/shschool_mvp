"""لوحةُ السكرتير — حضورُ اليوم وما ينتظره (قرارُ المالك 2026-10-02: الشريطان 1 و2).

الأرقامُ من الخدمات والمحدِّدات القائمة لا استعلاماتٍ مكرَّرة: كادرُ اليوم من ``recording_staff`` (بلا
المعفَيْن)، وحالاتُه من ``StaffAttendance``، وما ينتظر مرحلتَه من ``PermitService.awaiting``. وبصماتُ الدخول
الناقصةُ (كود 103) لا تُحفظ في المنصّة بل تُعرض في معاينة الاستيراد وحدَها، فلا مؤشّرَ لها هنا.

والبدلاءُ والتبديلاتُ شأنُ النائب (رأيُ المايسترو و0104) فلا تدخل هذه اللوحة، وكذلك أيُّ ما مصدرُه
يومُ 14 أو جاهزيّةُ التقرير الشهريّ قبل أن يثبت له مصدرٌ موثَّق.
"""

from __future__ import annotations

from datetime import date
from typing import Any

from django.db.models import Count
from django.urls import reverse
from django.utils import timezone

from core.models.audit import AuditLog
from core.models.school import School
from core.models.user import CustomUser

from .attendance import PermitService
from .attendance.exemptions import recording_staff
from .attendance.rules import SCHOOL_WEEKDAYS, STATUS_LABELS, STATUSES
from .models import LeaveRequest, StaffAttendance


def _tone(count: int, tone: str) -> str:
    return tone if count else "green"


def _last_import(school: School, today: date) -> dict[str, Any]:
    """آخرُ استيرادِ بصمةٍ للمدرسة، وهل غطّى اليوم — من أثر التدقيق لا من جدولٍ جديد."""
    logs = AuditLog.objects.filter(
        school=school, model_name="other", object_repr__startswith="BiometricImport"
    )
    last = logs.first()
    return {
        "last_import": last,
        "last_import_written": (last.changes or {}).get("written") if last else None,
        "last_import_at": timezone.localtime(last.timestamp) if last else None,
        "imported_today": logs.filter(object_repr__contains=today.isoformat()).exists(),
    }


def secretary_context(user: CustomUser, school: School, today: date) -> dict[str, Any]:
    roster = recording_staff(school, today)
    counts = dict.fromkeys(STATUSES, 0)
    for row in (
        StaffAttendance.objects.filter(school=school, date=today, staff__in=roster)
        .values("status")
        .annotate(n=Count("id"))
    ):
        counts[row["status"]] = row["n"]
    total = roster.count()
    counts["unmarked"] = total - sum(counts.values())

    board = reverse("staff_affairs:attendance_board")
    day = today.isoformat()
    attendance = [
        {
            "label": STATUS_LABELS.get(key, "لم يُرصد"),
            "value": counts[key],
            "tone": tone,
            "href": f"{board}?date={day}&status={key}",
            "title": title,
        }
        for key, tone, title in (
            ("present", "green", ""),
            ("late", "amber", ""),
            ("absent", "red", "غائبٌ بعد التاسعة بلا إذنٍ أو عذرٍ مقبول (البند 2.4)"),
            ("permitted", "sky", ""),
            ("unmarked", "maroon", "لم يُحسم أمرُه بعد — ليس غياباً حتى يُرصد"),
        )
    ]
    pending_leaves = LeaveRequest.objects.filter(school=school, status="pending").count()
    pending_permits = len(PermitService.awaiting(school, user))
    return {
        "view_type": "secretary",
        "is_school_day": today.weekday() in SCHOOL_WEEKDAYS,
        "attendance_total": total,
        "attendance": attendance,
        "pending_permits": pending_permits,
        "pending_leaves": pending_leaves,
        "permits_tone": _tone(pending_permits, "orange"),
        "leaves_tone": _tone(pending_leaves, "amber"),
        **_last_import(school, today),
    }

"""[STUDENT_AFFAIRS] W-20261114-009: لوحة «خارج الفصل الآن» وسجلّ الخروج التاريخي.

وحدةٌ مستقلّة عن `views.py` حفاظاً على سقف حجمه؛ والقراءةُ في `movement_selectors`.
لا تُكتب أسماءُ الطلبة في السجلّات.
"""

from __future__ import annotations

import datetime as dt
import uuid
from typing import Any

from django.contrib.auth.decorators import login_required
from django.shortcuts import render
from django.urls import reverse
from django.utils import timezone

from core.capabilities import capability_required, has_capability
from operations.class_exit import may_record_school_exit
from operations.models import ClassExit

from .movement_card import can_set_grace
from .movement_selectors import grace_rows, history_rows, incoming_rows, live_rows
from .movement_strip_selectors import destination_split, wing_strip

#: دورةُ تحديث اللوحة الحيّة بالثواني (HTMX) — «قادمون إليك» تتحدّث كلَّ 10 ثوانٍ.
REFRESH_SECONDS = 10


def live_context(request: Any, school: Any, scope: Any, day: dt.date) -> dict[str, Any]:
    """سياقُ اللوحة الحيّة: القادمون والخارجون الآن، وهل اليومُ المختار اليومُ (فيُفعَّل التحديثُ الذاتي)."""
    now = timezone.now()
    can_grace = can_set_grace(request.user)
    return {
        "incoming_rows": incoming_rows(school, scope, day, now),
        "live_rows": live_rows(school, scope, day, now),
        # شريطُ الأجنحة والتفصيلُ بالوجهة (W-20261119-003): العيادةُ تنفرد لمن عنده الملفُّ الصحّيّ الكامل فقط.
        "wing_strip": wing_strip(school, scope, day, now),
        "destination_split": destination_split(
            school, scope, day, has_capability(request.user, "clinic.health_full")
        ),
        "live_is_today": day == timezone.localdate(now),
        "live_refresh_seconds": REFRESH_SECONDS,
        "can_set_grace": can_grace,
        "grace_rows": grace_rows(school) if can_grace else [],
        # تغييرُ وجهة خروجٍ مفتوح (W-20261116-002): للمشرف والنائب والمدير، إلى ما عدا «الخروج من المدرسة».
        "can_change_destination": may_record_school_exit(request.user),
        "change_destinations": ClassExit.SUPERVISOR_DESTINATIONS,
    }


def _day(raw: str, default: dt.date) -> dt.date:
    try:
        return dt.date.fromisoformat(raw or "")
    except ValueError:
        return default


@login_required
@capability_required("student_affairs.follow_up")
def movements_live(request):
    """جزءُ HTMX: اللوحةُ الحيّة لليوم وحدَه، تُطلبه اللوحةُ كلَّ `REFRESH_SECONDS` ثانية."""
    from .views import _followup_scope

    scope = _followup_scope(request)
    ctx = live_context(request, request.school, scope, timezone.localdate())
    return render(request, "student_affairs/partials/movement_live.html", ctx)


@login_required
@capability_required("student_affairs.follow_up")
def movements_history(request):
    """السجلّ التاريخي: مرشِّحُ من تاريخ إلى تاريخ، وجدولٌ بكلّ طالبٍ وعدد خروجه ودقائقه بالوجهة."""
    from .views import _followup_scope

    today = timezone.localdate()
    start = _day(request.GET.get("start", ""), today - dt.timedelta(days=30))
    end = _day(request.GET.get("end", ""), today)
    student_id = request.GET.get("student", "")
    try:
        uuid.UUID(student_id)
    except ValueError:
        # معرّفٌ فاسدٌ أو غائبٌ في `?student=` لا يُسقط الصفحة — يُعامَل كأنّه غير موجود.
        student_id = ""
    rows = history_rows(request.school, _followup_scope(request), start, end, student_id)
    for row in rows:
        row["link"] = f"{reverse('student_affairs:movements_history')}?student={row['student'].pk}"
    return render(
        request,
        "student_affairs/movements_history.html",
        {"rows": rows, "start": start, "end": end, "student_id": student_id},
    )

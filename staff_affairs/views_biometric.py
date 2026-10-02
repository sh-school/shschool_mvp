"""استيرادُ كشف البصمة اليوميّ (لوحة السكرتير) — معاينةٌ ثمّ اعتمادٌ صريح.

العرضُ يقرأ الملفَّ ويستدعي ``attendance/biometric.py`` ويرسم؛ ولا قاعدةَ حضورٍ هنا.
مرحلتان لا واحدة لأنّ الحضورَ ينتهي خصماً من الراتب (البند 5): الكتابةُ لا تقع إلّا
بنقرة اعتمادٍ بعد أن يرى السكرتيرُ ما سيُكتب وما سيُتخطّى ولماذا.

والمعاينةُ المحفوظةُ في الجلسة أرقامٌ وظيفيّةٌ وأوقاتٌ فقط (بلا أسماءٍ ولا الملفّ نفسِه)،
وتنتهي بعد نصف ساعة أو بالاعتماد — والاسمُ يُقرأ من قاعدة المنصّة وقتَ العرض.
"""

from __future__ import annotations

import secrets
import time
from typing import Any, cast

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from core.capabilities import capability_required
from core.middleware import SchoolRequest

from .attendance import StaffAttendanceService, biometric, staff_members
from .forms import BiometricUploadForm

SESSION_KEY = "biometric_import"


def _context(request: HttpRequest) -> dict[str, Any]:
    school = cast(SchoolRequest, request).school
    if school is None or not StaffAttendanceService.can_record(school, request.user):  # type: ignore[arg-type]
        raise PermissionDenied("استيرادُ كشف البصمة للسكرتارية والمدير ومن ينوب عنه بتكليفه")
    return {"school": school, "form": BiometricUploadForm(), "today": timezone.localdate()}


@login_required
@capability_required("staff_affairs.attendance_import")  # type: ignore[misc]  # الحارسُ بلا أنواع في core
def attendance_import(request: HttpRequest) -> HttpResponse:
    """رفعُ الكشف ثمّ معاينتُه — لا كتابةَ في هذه الخطوة."""
    ctx = _context(request)
    if request.method == "POST":
        form = BiometricUploadForm(request.POST, request.FILES)
        ctx["form"] = form
        if form.is_valid():
            try:
                parsed = biometric.parse(form.cleaned_data["file"].read())
            except biometric.BiometricFileError as exc:
                ctx["error"] = str(exc)
            else:
                plan = biometric.preview(ctx["school"], request.user, parsed.rows, parsed.issues)  # type: ignore[arg-type]
                token = secrets.token_urlsafe(16)
                request.session[SESSION_KEY] = {
                    "token": token,
                    "school": str(ctx["school"].pk),
                    "at": time.time(),
                    "rows": [row.as_session() for row in parsed.rows],
                }
                ctx.update(plan=plan, token=token)
    return render(request, "staff_affairs/attendance_import.html", ctx)


@login_required
@capability_required("staff_affairs.attendance_import")  # type: ignore[misc]  # الحارسُ بلا أنواع في core
@require_POST
def attendance_import_commit(request: HttpRequest) -> HttpResponse:
    """الاعتماد: يُعاد حسابُ الخطّة من الحالة الراهنة ثمّ يُرصد ما أقرّته."""
    ctx = _context(request)
    saved = request.session.get(SESSION_KEY)
    fresh = (
        saved
        and secrets.compare_digest(str(saved.get("token", "")), request.POST.get("token", ""))
        and saved.get("school") == str(ctx["school"].pk)
        and time.time() - float(saved.get("at", 0)) <= biometric.PREVIEW_TTL_SECONDS
    )
    if not fresh:
        request.session.pop(SESSION_KEY, None)
        ctx["error"] = "انتهت المعاينةُ أو لم تعد صالحة — ارفع الملفَّ من جديد."
        return render(request, "staff_affairs/attendance_import.html", ctx)
    rows = [biometric.BiometricRow.from_session(r) for r in saved["rows"]]
    result = biometric.commit(
        ctx["school"],
        request.user,  # type: ignore[arg-type]
        rows,
        overwrite_conflicts=request.POST.get("overwrite_conflicts") == "1",
        request=request,
    )
    request.session.pop(SESSION_KEY, None)
    days = sorted({row.day for row in rows})
    if not result.failed:
        messages.success(
            request,
            f"رُصد {result.written} موظّفاً من كشف البصمة"
            + (f" وتُخطّي {result.skipped_same} مرصودون بالمثل." if result.skipped_same else "."),
        )
        board = reverse("staff_affairs:attendance_board")
        return redirect(f"{board}?date={days[0].isoformat()}" if len(days) == 1 else board)
    names = _names_by_number(ctx["school"], {row.employee_number for row, _ in result.failed})
    failed = [
        (names.get(row.employee_number, row.employee_number), msg) for row, msg in result.failed
    ]
    ctx.update(result=result, failed=failed, days=days)
    return render(request, "staff_affairs/attendance_import.html", ctx)


def _names_by_number(school: Any, numbers: set[str]) -> dict[str, str]:
    return {
        s.employee_number: s.full_name
        for s in staff_members(school).filter(employee_number__in=numbers)
    }

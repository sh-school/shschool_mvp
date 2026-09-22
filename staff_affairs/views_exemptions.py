"""الإعفاءُ من رصد الحضور اليوميّ — شاشةُ المدير ونائبه الإداريّ.

القواعدُ كلُّها في ``staff_affairs.attendance.exemptions.ExemptionService``؛ والعروضُ هنا
تقرأ الطلبَ وتُرجع الصفحة. (قرار المالك 2026-09-21، ق-16 في مواصفة الحضور.)
"""

from __future__ import annotations

from typing import cast
from uuid import UUID

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import Http404, HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from core.capabilities import capability_required
from core.middleware import SchoolRequest
from core.models.school import School
from core.models.user import CustomUser

from .attendance import ExemptionService, PolicyError
from .forms import AttendanceExemptionForm


def _school(request: HttpRequest) -> School:
    school = cast(SchoolRequest, request).school
    if school is None:
        raise Http404("لا مدرسةَ لهذا الحساب")
    return school


@login_required
@capability_required("staff_affairs.exemptions")  # type: ignore[misc]  # الحارسُ بلا أنواع في core
def staff_exemptions(request: HttpRequest) -> HttpResponse:
    """يعفي موظّفاً أو أكثر من الرصد اليوميّ، ويعرض القائمَ والسجلّ."""
    school, user = _school(request), cast(CustomUser, request.user)
    candidates = list(ExemptionService.candidates(school, user))
    form = AttendanceExemptionForm(
        request.POST if request.method == "POST" else None, candidates=candidates
    )
    if request.method == "POST" and form.is_valid():
        data = form.cleaned_data
        try:
            made = ExemptionService.grant(
                school=school,
                actor=user,
                staff_ids=data["staff"],
                start=data["start_date"],
                end=data["end_date"],
                reference=data["reference"],
                request=request,
            )
        except PolicyError as exc:
            form.add_error(None, str(exc))
        else:
            messages.success(request, f"أُعفي {len(made)} من الرصد اليوميّ.")
            return redirect("staff_affairs:exemptions")
    return render(
        request,
        "staff_affairs/exemptions.html",
        {
            "form": form,
            "candidates": candidates,
            "today": timezone.localdate(),
            **ExemptionService.screen(school),
        },
    )


@login_required
@capability_required("staff_affairs.exemptions")  # type: ignore[misc]  # الحارسُ بلا أنواع في core
@require_POST
def staff_exemption_revoke(request: HttpRequest, pk: UUID) -> HttpResponse:
    """رفعُ إعفاء — يبقى في السجلّ، ويسري أثرُه من اليوم لا بأثرٍ رجعيّ."""
    exemption = ExemptionService.one(_school(request), pk)
    try:
        ExemptionService.revoke(exemption, actor=cast(CustomUser, request.user), request=request)
    except PolicyError as exc:
        messages.error(request, str(exc))
    else:
        messages.success(request, "رُفع الإعفاءُ — ويعود الموظّفُ إلى لوحة الرصد من اليوم.")
    return redirect("staff_affairs:exemptions")

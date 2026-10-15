"""شاشاتُ إذن خروج الطالب — الطلبُ والاعتمادُ والاستمارة (W-20261005-010).

كلُّ ما يخصّ الشعبة خارج نطاق المستخدم 404 لا 403 (وجودُها في غير جناحه ليس شأنَه)؛ والقواعدُ في `wings/exit_permit.py`.
"""

from __future__ import annotations

import datetime as dt

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import Http404, HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from core.capabilities import capability_required
from core.export_utils import generate_export_filename
from core.models import CustomUser

from . import exit_permit as service
from . import exit_permit_form as form
from .exit_permit_print import render_permit


def _day(raw: str | None) -> dt.date:
    try:
        return dt.date.fromisoformat(raw or "")
    except ValueError:
        return timezone.localdate()


@login_required
@capability_required(service.REQUEST_CAP)
def exit_permit_list(request: HttpRequest) -> HttpResponse:
    day = _day(request.GET.get("date"))
    permits = service.permits_for(request.user, request.school, day)
    return render(
        request,
        "wings/exit_permits.html",
        {
            "permits": permits,
            "day": day,
            "min_periods": form.MIN_PERIODS_FOR_ATTENDANCE,
            "can_approve": service.can_approve(request.user),
        },
    )


@login_required
@capability_required(service.REQUEST_CAP)
def exit_permit_new(request: HttpRequest, student_id) -> HttpResponse:
    student = get_object_or_404(CustomUser, pk=student_id)
    try:
        class_group = service.current_class_of(student, request.school)
        if not service.may_request(request.user, request.school, class_group):
            raise service.PermitDeniedError
    except service.PermitDeniedError:
        raise Http404 from None
    if request.method == "POST":
        try:
            permit = service.request_permit(
                request.user,
                request.school,
                student,
                reason=request.POST.get("reason", ""),
                note=request.POST.get("note", ""),
            )
        except service.PermitDeniedError:
            raise Http404 from None
        except service.PermitError as exc:
            messages.error(request, str(exc))
        else:
            messages.success(request, f"سُجّل طلبُ إذن الخروج رقم {permit.sequence}.")
            return redirect("wings:exit_permit_list")
    return render(
        request,
        "wings/exit_permit_new.html",
        {"student": student, "class_group": class_group, "reasons": form.REASONS},
    )


@login_required
@capability_required(service.REQUEST_CAP)
@require_POST
def exit_permit_approve(request: HttpRequest, pk) -> HttpResponse:
    try:
        service.approve_permit(
            request.user,
            request.school,
            pk,
            guardian_present=request.POST.get("guardian_present") == "on",
        )
    except service.PermitDeniedError:
        raise Http404 from None
    except service.PermitError as exc:
        messages.error(request, str(exc))
    else:
        messages.success(request, "اعتُمد الإذن؛ يمكن طباعة الاستمارة للحارس.")
    return redirect("wings:exit_permit_list")


@login_required
@capability_required(service.REQUEST_CAP)
def exit_permit_pdf(request: HttpRequest, pk) -> HttpResponse:
    try:
        permit = service.own_permit(request.user, request.school, pk, approve=False)
    except service.PermitDeniedError:
        raise Http404 from None
    if permit.status != "approved":
        raise Http404
    response = HttpResponse(render_permit(request.user, permit), content_type="application/pdf")
    filename = generate_export_filename("wings", f"exit-permit-{permit.sequence}", "pdf")
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response

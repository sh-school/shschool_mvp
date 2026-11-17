"""شاشاتُ ورقة خروج الطالب — الإصدارُ المباشر والقائمةُ والاستمارة (W-20261005-010، W-20261116-003).

لا اعتمادَ في المنصّة: تُصدَر الورقةُ وتُطبع ويوقّعها بالقلم النائبُ الإداريّ أو المكلَّف بعمله.
كلُّ ما يخصّ الشعبة خارج نطاق المستخدم 404 لا 403 (وجودُها في غير جناحه ليس شأنَه)؛ والقواعدُ في `wings/exit_permit_services.py`.
"""

from __future__ import annotations

import datetime as dt

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import Http404, HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from core.audit_export import log_export
from core.capabilities import capability_required
from core.models import CustomUser
from core.pdf_utils import content_disposition

from . import exit_permit_form as form
from . import exit_permit_services as service
from .exit_permit_pdf_services import permit_pdf


def _day(raw: str | None) -> dt.date:
    try:
        return dt.date.fromisoformat(raw or "")
    except ValueError:
        return timezone.localdate()


def _posted_phone(post) -> str:
    """الرقمُ المختار من أرقام الوليّ المسجَّلة، أو المكتوبُ يدويّاً حين يُختار «رقمٌ آخر»."""
    choice = post.get("call_phone_choice", "")
    return post.get("call_phone_manual", "") if choice in ("", "other") else choice


@login_required
@capability_required(service.REQUEST_CAP)
def exit_permit_list(request: HttpRequest) -> HttpResponse:
    day = _day(request.GET.get("date"))
    permits = service.permits_for(request.user, request.school, day)
    for permit in permits:
        permit.printable = service.is_printable(permit)  # type: ignore[attr-defined]
    return render(
        request,
        "wings/exit_permits.html",
        {
            "permits": permits,
            "day": day,
            "min_periods": form.MIN_PERIODS_FOR_ATTENDANCE,
        },
    )


@login_required
@capability_required(service.REQUEST_CAP)
def exit_permit_new(request: HttpRequest, student_id) -> HttpResponse:
    student = get_object_or_404(CustomUser, pk=student_id)
    try:
        class_group = service.current_class_of(student, request.school)
        if not service.may_issue(request.user, request.school, class_group):
            raise service.PermitDeniedError
    except service.PermitDeniedError:
        raise Http404 from None
    if request.method == "POST":
        answer = request.POST.get("has_disability", "")
        try:
            if answer not in ("yes", "no"):
                raise service.PermitError("أجب عن سؤال: هل الطالب من ذوي الإعاقة؟")
            permit = service.issue_permit(
                request.user,
                request.school,
                student,
                reason=request.POST.get("reason", ""),
                note=request.POST.get("note", ""),
                guardian_method=request.POST.get("guardian_method", ""),
                call_phone=_posted_phone(request.POST),
                caller_name=request.POST.get("caller_name", ""),
                caller_relation=request.POST.get("caller_relation", ""),
                restricted=answer == "yes",
            )
        except service.PermitDeniedError:
            raise Http404 from None
        except service.PermitError as exc:
            messages.error(request, str(exc))
        else:
            messages.success(request, f"صدرت ورقة الخروج رقم {permit.sequence}؛ يمكن طباعتها.")
            if answer == "yes":
                # الجوابُ لا يُخزَّن ولا يُمرَّر: سطرُ الحضور يُطبع لكل ورقةٍ حضر فيها الوليّ
                return redirect("wings:exit_permit_pdf", permit.pk)
            return redirect("wings:exit_permit_list")
    return render(
        request,
        "wings/exit_permit_new.html",
        {
            "student": student,
            "class_group": class_group,
            "reasons": form.REASONS,
            "methods": form.GUARDIAN_METHODS,
            "phones": service.registered_phones(request.school, student),
            "posted": request.POST,
        },
    )


@login_required
@capability_required(service.REQUEST_CAP)
def exit_permit_pdf(request: HttpRequest, pk) -> HttpResponse:
    try:
        content, filename = permit_pdf(request.user, request.school, pk)
    except service.PermitDeniedError:
        raise Http404 from None
    response = HttpResponse(content, content_type="application/pdf")
    response["Content-Disposition"] = content_disposition(filename)
    log_export(request, "wings.exit_permit_pdf", rows=1, object_id=str(pk))
    return response

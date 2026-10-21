"""شاشةُ تسجيل نتيجة فترة الاختبار — قرارُ الإدارة (W-20261020-009).

القواعدُ كلُّها في ``staff_affairs.probation.record_result``؛ والعرضُ هنا يقرأ الطلبَ ويُرجع الصفحة.
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

from .probation import pending_results, record_result_audited
from .selectors import decided_probation_results, school_contract


def _school(request: HttpRequest) -> School:
    school = cast(SchoolRequest, request).school
    if school is None:
        raise Http404("لا مدرسةَ لهذا الحساب")
    return school


@login_required
@capability_required("staff_affairs.manage")  # type: ignore[misc]  # الحارسُ بلا أنواع في core
def probation_results(request: HttpRequest) -> HttpResponse:
    """العقودُ المنتهيةُ فترتُها وتنتظر نتيجةً، وآخرُ النتائج الصادرة."""
    school = _school(request)
    return render(
        request,
        "staff_affairs/probation_results.html",
        {"pending": pending_results(school), "decided": decided_probation_results(school)},
    )


@login_required
@capability_required("staff_affairs.manage")  # type: ignore[misc]  # الحارسُ بلا أنواع في core
@require_POST
def probation_result_record(request: HttpRequest, pk: UUID) -> HttpResponse:
    """يسجّل نجاحَ الموظف أو رسوبَه في الاختبار؛ ترفض الخدمةُ المبكّرَ والمكرَّر برسالةٍ عربيّة."""
    contract = school_contract(_school(request), pk)
    if contract is None:
        raise Http404("لا عقدَ بهذا المعرّف")
    try:
        record_result_audited(
            contract,
            request.POST.get("result", ""),
            cast(CustomUser, request.user),
            timezone.localdate(),
            request=request,
        )
    except ValueError as exc:
        messages.error(request, str(exc))
    else:
        messages.success(request, f"سُجّلت نتيجة الاختبار لـ{contract.staff.full_name}.")
    return redirect("staff_affairs:probation_results")

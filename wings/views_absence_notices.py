"""تنبيهات الغياب المحجوزة وزرّ «إصدار الإخطار» لحاصر الغياب (قرارُ المالك D-246م) — القواعدُ كلُّها في `absence_notices`."""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import Http404
from django.shortcuts import redirect, render
from django.views.decorators.http import require_POST

from core.capabilities import capability_required

from . import absence_notice_services as absence_notices
from .services import holds_school_wide


def _require_holder(request):
    if not holds_school_wide(request.user):
        raise Http404  # لا يُكشف وجودُ الشاشة لغير الحاصر


@login_required
@capability_required("wings.record_day")
def absence_notice_list(request):
    _require_holder(request)
    return render(
        request,
        "wings/absence_notices.html",
        {"alerts": absence_notices.held_alerts(request.school)},
    )


@login_required
@capability_required("wings.record_day")
@require_POST
def absence_notice_issue(request, alert_id):
    _require_holder(request)
    ok, text = absence_notices.issue_message(request.user, request.school, alert_id)
    (messages.success if ok else messages.error)(request, text)
    return redirect("wings:absence_notices")

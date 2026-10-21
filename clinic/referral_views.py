"""
clinic/referral_views.py — قائمةُ الإحالات وإيصالُها (W-20261020-038)
══════════════════════════════════════════════════════════════════════
للممرّض وحدَه (`clinic.write`): القائمةُ فيها أسماءُ طلبةٍ، والإيصالُ لا يُعرض لغيره، وكلُّ فتحٍ للإيصال
(الذي منه تكون الطباعة) يُسجَّل في سجلّ التدقيق بالرقم التسلسليّ. بلا تخزين (`never_cache`).
"""

from __future__ import annotations

from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET, require_POST

from clinic import choices
from clinic.models import ClinicReferral
from clinic.referrals import close_referral, mask_person_name
from core.capabilities import capability_required
from core.models.audit import AuditLog

_guard = (login_required, capability_required("clinic.write"), never_cache)


def _protected(view):
    for deco in reversed(_guard):
        view = deco(view)
    return view


def _party_label(code: str) -> str:
    return dict(choices.FOLLOWUP_CHOICES).get(code, "")


@_protected
@require_GET
def referrals_list(request):
    school = request.user.get_school()
    rows = list(
        ClinicReferral.objects.filter(school=school).select_related("visit__student", "closed_by")
    )
    labels = dict(choices.FOLLOWUP_CHOICES)
    results = dict(choices.REFERRAL_RESULT_CHOICES)
    for r in rows:
        r.party_label = labels.get(r.follow_up_party, "")
        r.result_label = results.get(r.result_code, "")
    return render(
        request,
        "clinic/referrals.html",
        {
            "open_rows": [r for r in rows if r.status == choices.REFERRAL_OPEN],
            "closed_rows": [r for r in rows if r.status == choices.REFERRAL_CLOSED],
            "result_choices": choices.REFERRAL_RESULT_CHOICES,
        },
    )


@_protected
@require_POST
def referral_close(request, referral_id):
    referral = get_object_or_404(ClinicReferral, id=referral_id, school=request.user.get_school())
    try:
        close_referral(referral, request.POST.get("result", ""), request.user)
    except ValueError:
        return HttpResponse("طلبٌ غير صالح", status=400)
    return redirect("clinic:referrals")


@_protected
@require_GET
def referral_receipt(request, referral_id):
    school = request.user.get_school()
    referral = get_object_or_404(
        ClinicReferral.objects.select_related("visit__student"), id=referral_id, school=school
    )
    AuditLog.log(
        user=request.user,
        action="export",
        model_name="other",
        object_id=str(referral.id),
        object_repr=f"clinic.referral_receipt #{referral.serial_no}",
        changes={"kind": "clinic.referral_receipt", "serial_no": referral.serial_no},
        school=school,
        request=request,
    )
    return render(
        request,
        "clinic/referral_receipt.html",
        {
            "referral": referral,
            "masked_name": mask_person_name(referral.visit.student.full_name),
            "party_label": _party_label(referral.follow_up_party),
            "printed_on": timezone.localdate(),
        },
    )

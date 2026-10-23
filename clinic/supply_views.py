"""
clinic/supply_views.py — قائمةُ صلاحية مستلزمات العيادة (W-20261020-040)
════════════════════════════════════════════════════════════════════════
للممرّض وحدَه (`clinic.write`). القائمةُ مرتّبةٌ بأقرب انتهاء، والحالةُ (30/60/منتهٍ) نصٌّ لا لونٌ وحدَه.
لا خصمَ تلقائياً ولا حذفَ تلقائياً: الإدخالُ والحذفُ يدويّان بـPOST.
لا بياناتَ شخصيّةً في هذه الشاشة، فلا تُصنَّف صحّيّةً في حارس التدقيق.
"""

from __future__ import annotations

from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET, require_POST

from clinic.forms import ClinicSupplyItemForm
from clinic.models import ClinicSupplyItem
from clinic.supplies import annotated_items
from core.capabilities import capability_required

_guard = (login_required, capability_required("clinic.write"), never_cache)


def _protected(view):
    for deco in reversed(_guard):
        view = deco(view)
    return view


@_protected
@require_GET
def supplies_list(request):
    return render(
        request,
        "clinic/supplies.html",
        {"items": annotated_items(request.school), "form": ClinicSupplyItemForm()},
    )


@_protected
@require_POST
def supply_add(request):
    form = ClinicSupplyItemForm(request.POST)
    if not form.is_valid():
        return render(
            request,
            "clinic/supplies.html",
            {"items": annotated_items(request.school), "form": form},
            status=400,
        )
    ClinicSupplyItem.objects.create(school=request.school, **form.cleaned_data)
    return redirect("clinic:supplies")


@_protected
@require_POST
def supply_delete(request, item_id):
    get_object_or_404(ClinicSupplyItem, id=item_id, school=request.school).delete()
    return redirect("clinic:supplies")

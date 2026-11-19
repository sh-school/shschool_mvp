"""[STUDENT_AFFAIRS] W-20261119-002: إجراءاتُ بطاقة الخروج من شاشة الحركة — مُهَلُ الوجهات والتحويلُ إلى متابعة.

وحدةٌ مستقلّة عن `views.py` حفاظاً على سقف حجمه؛ والكتابةُ في `operations.exit_card`. لا أسماءَ في السجلّات.
"""

from __future__ import annotations

from typing import Any

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404, redirect
from django.views.decorators.http import require_POST

from core.capabilities import capability_required, has_capability
from operations import exit_card
from operations.models import ClassExit
from wings.scope import student_scope_for

#: من يضبط مُهَلَ الوجهات: المدير والنائبُ والمنسّق (قدرةُ إدارة شؤون الطلبة).
GRACE_CAP = "student_affairs.manage"


def can_set_grace(user: Any) -> bool:
    return has_capability(user, GRACE_CAP)


def _minutes_of(raw: str) -> int | None:
    """دقائقُ المهلة من حقلٍ نصّيّ: فراغٌ = بلا مهلة، وغيرُ الرقميّ أو غيرُ الموجب خطأ."""
    text = (raw or "").strip()
    if not text:
        return None
    if not text.isdigit() or int(text) < 1 or int(text) > 240:
        raise ValueError("المهلةُ عددٌ من 1 إلى 240 دقيقة.")
    return int(text)


@login_required
@capability_required("student_affairs.follow_up")
@require_POST
def movement_grace_save(request):
    """يحفظ مُهَلَ الوجهات الخمس دفعةً واحدة — الحقلُ الفارغ يمحو مهلةَ وجهته."""
    if not can_set_grace(request.user):
        raise PermissionDenied("ضبطُ مُهَل الوجهات للمدير والنائب والمنسّق.")
    try:
        chosen = {
            code: _minutes_of(request.POST.get(f"grace_{code}", ""))
            for code, _ in exit_card.GRACE_DESTINATIONS
        }
    except ValueError as exc:
        messages.error(request, str(exc))
        return redirect("student_affairs:student_movements")
    for code, minutes in chosen.items():
        exit_card.set_grace(request.school, code, minutes, request.user)
    messages.success(request, "حُفظت مُهَل الوجهات.")
    return redirect("student_affairs:student_movements")


@login_required
@capability_required("student_affairs.follow_up")
@require_POST
def movement_followup(request, pk):
    """«تحويل إلى متابعة» بسببٍ مكتوب — وخارجُ نطاق الجناح 404. لا مخالفةَ تُنشأ منه."""
    scope = student_scope_for(request)
    exit_ = get_object_or_404(
        scope.narrow(ClassExit.objects.filter(school=request.school)).select_related("school"),
        pk=pk,
    )
    try:
        done = exit_card.refer_to_followup(exit_, request.POST.get("reason", ""), request.user)
    except ValueError as exc:
        messages.error(request, str(exc))
    else:
        messages.success(
            request, "حُوّل إلى المتابعة." if done else "حُوّل هذا الخروج إلى المتابعة من قبل."
        )
    return redirect("student_affairs:student_movements")

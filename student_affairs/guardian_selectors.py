"""قراءاتُ شاشات طلبات الأولياء — كلُّ استعلامٍ مفلترٌ بمدرسة الطلب (W-20261001-019).

العروضُ لا تبني استعلاماً (سقّاطةُ الطبقات)؛ فهنا يُبنى ويُقيَّم، وما يُرجَع قوائمُ أو كائناتٌ. والكائنُ
غيرُ الموجود في المدرسة `Http404` لا «لا شيء»، فطلبُ مدرسةٍ أخرى لا يُكشف وجودُه.
"""

from __future__ import annotations

import uuid

from django.http import Http404
from django.shortcuts import get_object_or_404

from core.models.access import Membership
from core.models.user import CustomUser

from .guardian_request_models import GuardianRequest

LIST_LIMIT = 100


def list_requests(school, kind: str = "", stage: str = "") -> list[GuardianRequest]:
    """الأحدثُ أولاً، مرشَّحاً بالنوع والمرحلة إن عُرفا (غيرُ المعروف يُهمَل لا يُخطئ)."""
    queryset = GuardianRequest.objects.filter(school=school).select_related("student")
    if kind in dict(GuardianRequest.KIND_CHOICES):
        queryset = queryset.filter(kind=kind)
    if stage in dict(GuardianRequest.STAGE_CHOICES):
        queryset = queryset.filter(stage=stage)
    return list(queryset[:LIST_LIMIT])


def get_request(school, pk) -> GuardianRequest:
    return get_object_or_404(
        GuardianRequest.objects.select_related(
            "student", "referred_to", "feedback_by", "verified_by"
        ),
        pk=pk,
        school=school,
    )


def events_of(req: GuardianRequest) -> list:
    return list(req.events.select_related("actor"))


def staff_options(school) -> list[Membership]:
    """من يُحوَّل إليهم الطلب: كلُّ عضويّةٍ نشطةٍ في المدرسة عدا الطلبة وأولياء الأمور."""
    return list(
        Membership.objects.filter(school=school, is_active=True)
        .exclude(role__name__in=["student", "parent"])
        .select_related("user")
        .order_by("user__full_name")
    )


def school_member(school, raw_id) -> CustomUser:
    """عضوٌ نشطٌ في المدرسة بمعرّفه — معرّفٌ مشوَّهٌ أو من مدرسةٍ أخرى 404."""
    try:
        member_id = raw_id if isinstance(raw_id, uuid.UUID) else uuid.UUID(str(raw_id))
    except ValueError:
        raise Http404 from None
    return get_object_or_404(
        CustomUser,
        id=member_id,
        memberships__school=school,
        memberships__is_active=True,
    )

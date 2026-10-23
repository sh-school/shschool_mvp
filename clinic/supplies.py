"""clinic/supplies.py — قائمةُ صلاحية مستلزمات العيادة وتنبيهُ الممرّض (W-20261020-040)

العتبتان 30 و60 يوماً قرارُ منصّةٍ لا لائحةٌ نظاميّة (ملاحظة 0301). التصنيفُ دالّةٌ نقيّةٌ من تاريخ الانتهاء والتاريخ الحاليّ،
ولا يخصم شيءٌ من الكمّيّة ولا يُحذف صنفٌ بانقضاء صلاحيته: القرارُ للممرّض.

التنبيهُ مهمّةٌ خلفيّةٌ يومية: إشعارٌ داخل المنصّة لكلّ ممرّضٍ مرّةً لكلّ (صنف، فئة) — فيصله عند دخول الصنف 60 يوماً ثمّ عند دخوله 30 ثمّ عند الانتهاء،
لا كلَّ يوم. **الجدولةُ معطَّلةٌ افتراضياً** — `CLINIC_SUPPLY_BEAT=1` وحدَه (`supply_beat.py`) بعد إعادة نشر beat بأمر المالك.
"""

from __future__ import annotations

import datetime as dt
from typing import TYPE_CHECKING

from django.utils import timezone

from clinic.models import ClinicSupplyItem

if TYPE_CHECKING:
    from core.models import School

SOON_DAYS = 30
WARNING_DAYS = 60

EXPIRED = "expired"
SOON = "soon"
WARNING = "warning"
OK = "ok"

#: الفئة ← (النصّ، صنفُ الشارة). النصُّ يحمل المعنى؛ اللونُ تعزيزٌ فقط.
STATE_LABELS = {
    EXPIRED: ("منتهي الصلاحية", "badge--danger"),
    SOON: ("ينتهي خلال 30 يوماً", "badge--danger"),
    WARNING: ("ينتهي خلال 60 يوماً", "badge--warning"),
    OK: ("سليم", "badge--success"),
}


def classify(expiry: dt.date, today: dt.date) -> str:
    """فئةُ الصنف: منتهٍ (قبل اليوم)، أو ≤30 يوماً، أو ≤60، وإلا سليم. يومُ الانتهاء نفسُه ما زال صالحاً."""
    days = (expiry - today).days
    if days < 0:
        return EXPIRED
    if days <= SOON_DAYS:
        return SOON
    if days <= WARNING_DAYS:
        return WARNING
    return OK


def annotated_items(school: School, today: dt.date | None = None) -> list[ClinicSupplyItem]:
    """أصنافُ المدرسة مرتّبةً بأقرب انتهاءٍ، وعلى كلٍّ منها `state` و`state_label` و`state_class` و`days_left`."""
    today = today or timezone.localdate()
    items = list(ClinicSupplyItem.objects.filter(school=school).order_by("expiry_date", "name"))
    for item in items:
        item.state = classify(item.expiry_date, today)  # type: ignore[attr-defined]
        item.state_label, item.state_class = STATE_LABELS[item.state]  # type: ignore[attr-defined]
        item.days_left = (item.expiry_date - today).days  # type: ignore[attr-defined]
    return items


def alert_nurses(school: School, today: dt.date | None = None) -> int:
    """ينبّه ممرّضي المدرسة بالأصناف المنتهية أو القريبة من الانتهاء — مرّةً لكلّ (ممرّض، صنف، فئة). يُرجع عددَ الإشعارات."""
    from core.models import Membership
    from notifications.hub import NotificationHub
    from notifications.models import InAppNotification

    today = today or timezone.localdate()
    due = [
        i
        for i in annotated_items(school, today)
        if i.state != OK and i.quantity > 0  # type: ignore[attr-defined]
    ]
    if not due:
        return 0
    nurses = [
        m.user
        for m in Membership.objects.filter(
            school=school, role__name="nurse", is_active=True
        ).select_related("user")
    ]
    if not nurses:
        return 0
    keys = {f"{i.pk}:{i.state}" for i in due}  # type: ignore[attr-defined]
    sent = set(
        InAppNotification.objects.filter(
            user__in=nurses, event_type="clinic", related_object_id__in=keys
        ).values_list("user_id", "related_object_id")
    )
    created = 0
    for item in due:
        key = f"{item.pk}:{item.state}"  # type: ignore[attr-defined]
        todo = [n for n in nurses if (n.pk, key) not in sent]
        if not todo:
            continue
        label, _ = STATE_LABELS[item.state]  # type: ignore[attr-defined]
        result = NotificationHub.dispatch(
            event_type="clinic_expiry",
            school=school,
            recipients=todo,
            title=f"مستلزمات العيادة: {item.name} — {label}",
            body=f"تاريخ الانتهاء {item.expiry_date:%Y-%m-%d}، الكمّيّة {item.quantity}. القرارُ لك: لا يُخصم شيءٌ تلقائياً.",
            related_url="/clinic/supplies/",
            related_object_id=key,
        )
        created += int(result.get("in_app", 0))
    return created

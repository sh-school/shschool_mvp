"""بطاقةُ الخروج: الوصولُ والعودةُ ومُهَلُ الوجهات وتأخّرُ العودة وتصعيدُ ما لم يُستلَم (إدارةُ الأجنحة 2/4).

قراراتُ المالك 2026-11-19، على `ClassExit` نفسِه لا كيانٌ جديد:

- **وصل**: اختيارُ المشرف للوجهة يسجّله بنقرةٍ واحدة، بشرطٍ ذرّيٍّ `routed_at IS NULL` فلا يسبق أحدُهما الآخر.
- **عاد**: يسجّلها المشرفان ومعلّمُ الحصّة الجارية ولو لم يكن المُخرِج. العودةُ الثانيةُ لا تفعل شيئاً وتُظهر من
  سجّلها (`select_for_update`). الوقتُ من النقرة فقط.
- **المهلة**: إعدادٌ مدرسيٌّ لكلّ وجهة (`ExitDestinationGrace`)؛ تُلتقَط لقطةً في `allowed_minutes` لحظةَ الوصول.
  العيادةُ والإدارةُ والنائبُ والمنسّقُ بلا مهلة. تأخّرُ العودة = ما بعد المهلة، ويُكتب في `late_return_seconds`.
  الإغلاقُ بالجرس `system_closed` «مجهول» ولا يُحسب تأخّراً.
- لا مخالفةَ سلوكيّةً تُنشأ من التأخّر، ولا يدخل `late_minutes` في الحضور (`presence.py` لا يتغيّر).

لا نصَّ في الدليل التنظيميّ (`08_conduct_policy_2026.md`) يحدّد مُهَلَ العودة من الوجهات ولا مدّةَ التصعيد؛ فهي إعدادٌ
وقرارٌ من المالك لا رقمٌ لائحيّ، ولا رقمَ افتراضيّاً للمهلة: الوجهةُ بلا إعدادٍ بلا مهلة.
"""

from __future__ import annotations

import datetime as dt
import logging
from typing import TYPE_CHECKING, Any

from django.db import transaction
from django.utils import timezone

from operations.models import ClassExit, ExitDestinationGrace

if TYPE_CHECKING:
    from core.models import CustomUser, School

logger = logging.getLogger(__name__)

#: الوجهاتُ التي تقبل مهلةً. ما عداها (العيادة، المنسّق، النائب، الإدارة، مشرف الجناح) بلا مهلة.
GRACE_DESTINATIONS = [
    ("restroom", "دورة المياه"),
    ("arts", "الفنون البصرية"),
    ("lab_cs", "معمل الحاسوب"),
    ("lab_sci", "معمل العلوم"),
    ("pe", "التربية البدنية"),
]

#: دقائقُ الانتظار بلا استلامٍ قبل كلّ مرحلةِ تصعيد: المشرفُ الآخر عند الأولى، ثمّ النائبُ الإداريّ عند الثانية.
ESCALATE_STEP_MINUTES = 5


def grace_minutes_for(school: School, destination: str) -> int | None:
    """مهلةُ الوجهة في المدرسة بالدقائق — أو `None` لوجهةٍ بلا مهلةٍ أو لم تُضبط."""
    if destination not in dict(GRACE_DESTINATIONS):
        return None
    return (
        ExitDestinationGrace.objects.filter(school=school, destination=destination)
        .values_list("minutes", flat=True)
        .first()
    )


@transaction.atomic
def set_grace(school: School, destination: str, minutes: int | None, by: CustomUser) -> None:
    """يضبط مهلةَ وجهةٍ (أو يمحوها بـ`None`) — ويُسجَّل في سجلّ المراجعة. لا يمسّ ما التُقط من قبل."""
    if destination not in dict(GRACE_DESTINATIONS):
        raise ValueError("وجهةٌ لا تقبل مهلة.")
    if minutes is None:
        ExitDestinationGrace.objects.filter(school=school, destination=destination).delete()
    else:
        if minutes < 1:
            raise ValueError("المهلةُ دقيقةٌ فأكثر.")
        ExitDestinationGrace.objects.update_or_create(
            school=school, destination=destination, defaults={"minutes": minutes}
        )
    _audit(
        by,
        school,
        "setting",
        f"مهلة وجهة {destination}",
        {"destination": destination, "minutes": minutes},
    )


def _audit(user: Any, school: Any, what: str, label: str, changes: dict[str, Any]) -> None:
    """سطرُ مراجعةٍ بلا أسماءٍ ولا نصٍّ حرّ: معرّفاتٌ وأرقامٌ فقط."""
    from core.models import AuditLog

    AuditLog.objects.create(
        user=user,
        school=school,
        action="update",
        model_name="other",
        object_id=str(changes.get("exit", ""))[:100],
        object_repr=f"بطاقة خروج — {label}"[:300],
        changes={"what": what, **changes},
    )


def late_seconds(exit_: ClassExit, returned_at: dt.datetime) -> int | None:
    """ثوانٍ بعد المهلة عند العودة — `None` إن لم يصل بعد أو بلا مهلة. (10 دقائق ومهلة 7 ⇒ 180)."""
    if exit_.routed_at is None or exit_.allowed_minutes is None:
        return None
    due = exit_.routed_at + dt.timedelta(minutes=exit_.allowed_minutes)
    return max(0, int((returned_at - due).total_seconds()))


def role_of_returner(exit_: ClassExit, by: CustomUser | None) -> str:
    """دورُ من سجّل العودة بالنسبة لهذا الخروج: المعلّم أو أحدُ حاملَي الجناح أو العيادة، وبلا مستخدمٍ فالنظام."""
    if by is None:
        return "system"
    group = exit_.session.class_group
    if group.wing_id:
        holders = group.wing.holders(exit_.session.date)
        if holders.field is not None and holders.field.pk == by.pk:
            return "field_supervisor"
        if holders.supervisor is not None and holders.supervisor.pk == by.pk:
            return "wing_supervisor"
    role = by.get_role()  # type: ignore[no-untyped-call]
    if role == "teacher":
        return "teacher"
    if role == "nurse":
        return "clinic"
    return "wing_supervisor"


def route(
    exit_: ClassExit, destination: str, by: CustomUser, now: dt.datetime | None = None
) -> bool:
    """يسجّل «وصل» عند اختيار المشرف للوجهة — ويُرجع هل هذه النقرةُ هي التي سجّلته.

    الوجهةُ تُحدَّث دائماً (تغييرُ الوجهة)، أمّا الوصولُ فمرّةٌ واحدة: الشرطُ الذرّيُّ `routed_at IS NULL`
    في الـUPDATE نفسِه. والمهلةُ تُلتقَط لقطةً من وجهة هذه النقرة.
    """
    now = now or timezone.now()
    allowed = grace_minutes_for(exit_.school, destination)
    won = ClassExit.objects.filter(
        pk=exit_.pk, routed_at__isnull=True, returned_at__isnull=True
    ).update(destination=destination, routed_at=now, routed_by=by, allowed_minutes=allowed)
    if not won:
        ClassExit.objects.filter(pk=exit_.pk, returned_at__isnull=True).update(
            destination=destination, allowed_minutes=allowed
        )
    exit_.refresh_from_db()
    return bool(won)


@transaction.atomic
def return_exit(
    exit_id: Any, by: CustomUser | None, now: dt.datetime | None = None
) -> tuple[ClassExit | None, bool]:
    """«عاد» بنقرة — (السطر، هل سجّلتُه أنا). الثانيةُ لا تفعل شيئاً وتُرجع السطرَ بمن سجّله.

    السطرُ يُقفَل (`select_for_update`) فيتسلسل ضغطُ مشرفَين معاً: يسجّل الأوّلُ ويرى الثاني اسمَه.
    """
    exit_ = (
        ClassExit.objects.select_for_update(of=("self",))
        .select_related("session__class_group__wing", "student", "school")
        .filter(pk=exit_id)
        .first()
    )
    if exit_ is None:
        return None, False
    if exit_.returned_at is not None:
        return exit_, False
    close_with_return(exit_, by, now)
    return exit_, True


def close_with_return(
    exit_: ClassExit, by: CustomUser | None, now: dt.datetime | None = None
) -> None:
    """يكتب العودةَ على سطرٍ مقفولٍ مفتوح: الوقتُ والمُسجِّلُ ودورُه والتأخّرُ، وسجلَّ المراجعة."""
    moment = now or timezone.now()
    exit_.returned_at = moment
    exit_.returned_by = by
    exit_.returned_by_role = role_of_returner(exit_, by)
    exit_.late_return_seconds = late_seconds(exit_, moment)
    exit_.save(
        update_fields=["returned_at", "returned_by", "returned_by_role", "late_return_seconds"]
    )
    if by is not None:
        _audit(
            by,
            exit_.school,
            "return",
            "عودة طالب",
            {"exit": str(exit_.pk), "by": str(by.pk), "role": exit_.returned_by_role},
        )


@transaction.atomic
def refer_to_followup(
    exit_: ClassExit, reason: str, by: CustomUser, now: dt.datetime | None = None
) -> bool:
    """«تحويل إلى متابعة» بسببٍ مكتوب — يُحفَظ على السطر. السببُ الفارغُ مرفوض. لا مخالفةَ تُنشأ."""
    text = (reason or "").strip()
    if not text:
        raise ValueError("اكتب سببَ التحويل إلى المتابعة.")
    done = ClassExit.objects.filter(pk=exit_.pk, followup_at__isnull=True).update(
        followup_reason=text, followup_at=now or timezone.now()
    )
    if done:
        # السببُ نصٌّ حرٌّ قد يحمل ما لا يجوز في السجلّ: يُسجَّل طولُه لا نصُّه.
        _audit(
            by,
            exit_.school,
            "followup",
            "تحويل خروج إلى متابعة",
            {"exit": str(exit_.pk), "by": str(by.pk), "reason_chars": len(text)},
        )
    return bool(done)


def _recipients_for_stage(exit_: ClassExit, stage: int) -> list[Any]:
    """المرحلة 1: المشرفُ الآخر (الميدانيّ)، والمرحلة 2: النائبُ الإداريّ."""
    if stage == 1:
        wing = exit_.session.class_group.wing
        other = wing.holders(exit_.session.date).field if wing is not None else None
        return [other] if other is not None else []
    from core.models import Membership

    members = Membership.objects.filter(
        school=exit_.school, role__name="vice_admin", is_active=True
    ).select_related("user")
    return [m.user for m in members]


def escalate_unreceived(school: School, now: dt.datetime) -> int:
    """يصعّد بطاقاتِ اليوم التي لم يُحدَّد لها وجهةٌ (لم تُستلَم) — ويُرجع عددَ التنبيهات المرسَلة.

    مرحلةٌ كلَّ `ESCALATE_STEP_MINUTES`: المشرفُ الآخر ثمّ النائب، وكلُّ مرحلةٍ **مرّةً واحدة**: الانتقالُ ذرّيٌّ
    (`alert_stage = n` ⇒ `n+1`) فتكرارُ المهمّة أو تزامنُها لا يضاعف التنبيه. ومن لا مستلمَ له تُحتسب مرحلتُه ولا يتعطّل ما بعدها.
    """
    sent = 0
    open_cards = ClassExit.objects.filter(
        school=school,
        session__date=timezone.localdate(now),
        routed_at__isnull=True,
        returned_at__isnull=True,
        destination="wing_sup",
        alert_stage__lt=2,
    ).select_related("session__class_group__wing", "student", "school")
    for exit_ in open_cards:
        stage = exit_.alert_stage + 1
        waited = (now - exit_.left_at).total_seconds()
        if waited < stage * ESCALATE_STEP_MINUTES * 60:
            continue
        claimed = ClassExit.objects.filter(
            pk=exit_.pk, alert_stage=exit_.alert_stage, routed_at__isnull=True
        ).update(alert_stage=stage)
        if not claimed:
            continue
        sent += _alert(exit_, _recipients_for_stage(exit_, stage), stage)
    return sent


def _alert(exit_: ClassExit, recipients: list[Any], stage: int) -> int:
    """إشعارُ التصعيد — لا يُسقط المهمّة إن تعذّر. بلا أسماءٍ في السجلّات."""
    if not recipients:
        return 0
    try:
        from django.urls import reverse

        from notifications.hub import NotificationHub

        who = "النائب الإداريّ" if stage == 2 else "المشرف"
        NotificationHub.dispatch(
            event_type="class_exit",
            school=exit_.school,
            recipients=recipients,
            title=f"طالبٌ بلا استلام — {exit_.student.full_name}",
            body=(
                f"{exit_.student.full_name} ({exit_.session.class_group}) بانتظار تحديد الوجهة "
                f"منذ {stage * ESCALATE_STEP_MINUTES} دقائق على الأقلّ — تنبيهٌ إلى {who}."
            ),
            priority="high",
            related_url=reverse("student_affairs:student_movements"),
            related_object_id=str(exit_.pk),
        )
    except Exception as exc:  # noqa: BLE001 — التنبيهُ تابعٌ للبطاقة لا شرطٌ لها
        logger.warning("exit_card: تعذّر تنبيه التصعيد [exit=%s stage=%s]: %s", exit_.pk, stage, exc)
        return 0
    return len(recipients)

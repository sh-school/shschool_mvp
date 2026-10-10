"""breach/services.py — تسجيلُ الخرق وانتقالاتُ حالته (PDPPL م.14 + إرشاد NCSA 72h).

وقتُ إشعار NCSA (`ncsa_notified_at`) هو المعتمَد قانونيّاً في احتساب الالتزام بالمهلة؛
فيُختم مرّةً واحدةً تحت قفلِ الصفّ، وكلُّ انتقالٍ يُدقَّق في `AuditLog`.
"""

import logging

from django.db import transaction
from django.utils import timezone

from core.models import AuditLog, BreachReport

logger = logging.getLogger(__name__)

NCSA_TEMPLATE = """إلى: المركز الوطني للأمن السيبراني (NCSA)
الموضوع: إشعار بخرق بيانات — PDPPL م.11

المؤسسة: {organization}
التاريخ: {date}

1. طبيعة الخرق: {title}
2. وقت الاكتشاف: {discovered_at}
3. البيانات المتأثرة: {data_type}
4. عدد الأشخاص المتأثرين: {affected_count}
5. الإجراءات الفورية المتخذة: {immediate_action}
6. خطة الاحتواء: {containment}

نؤكد التزامنا بالإجراءات المنصوص عليها في قانون حماية البيانات الشخصية رقم 13/2016.
""".strip()


_EMPTY = "لم يُسجَّل بعد"


def build_ncsa_text(breach: BreachReport) -> str:
    """نصُّ إشعار NCSA مملوءاً من بيانات الخرق. لا يُرسَل شيء: الإرسالُ قرارُ المسؤول."""
    return NCSA_TEMPLATE.format(
        organization=breach.school.name,
        date=timezone.localdate(),
        title=breach.title,
        discovered_at=f"{timezone.localtime(breach.discovered_at):%Y/%m/%d %H:%M}",
        data_type=breach.get_data_type_affected_display(),
        affected_count=breach.affected_count,
        immediate_action=breach.immediate_action.strip() or _EMPTY,
        containment=breach.containment_action.strip() or _EMPTY,
    )


#: الانتقالاتُ المسموحة. الإغلاقُ بلا إشعارٍ يُسمح به من «قيد التقييم» وحدَه (خلصَ التقييمُ إلى
#: أنّ الخرقَ لا يستوجب إشعاراً) ويُدقَّق بعلامةٍ صريحة؛ ومن «مكتشَف» لا — لم يُقيَّم بعد.
ALLOWED_TRANSITIONS = {
    "discovered": {"assessing", "notified"},
    "assessing": {"notified", "resolved"},
    "notified": {"resolved"},
    "resolved": set(),
}


class InvalidTransitionError(Exception):
    """انتقالٌ غيرُ مسموح — الرسالةُ عربيّةٌ تُعرض للمستخدم كما هي."""


ASSIGNED_TITLE = "أُسنِد إليك بلاغُ خرقِ بيانات"


def notify_assignee(breach: BreachReport, *, assignee, by=None) -> bool:
    """يُنبّه المكلَّفَ بالبلاغ عبر `NotificationHub` — يُعيد: أأُرسل؟ (DBT-24، PDPPL م.11).

    لا إشعارَ لمن أسند نفسَه (`assignee == by`) ولا لحسابٍ معطَّل. **والنصُّ بلا بياناتٍ شخصيّة ولا عنوانِ البلاغ**:
    خطورةٌ ومهلةٌ ورابط، كتنبيه المهلة القائم (`notifications.tasks._notify_breach_in_app`). وعطلُ الإشعار **لا يُسقط**
    التسجيلَ ولا التعديل (يُسجَّل خطأً يراه Sentry) — في نقطةِ حفظٍ صغيرةٍ كي لا يُفسد معاملةَ المتّصل إن سقط الاستعلام.
    """
    if assignee is None or not assignee.is_active:
        return False
    if by is not None and assignee.pk == by.pk:
        return False
    body = f"الخطورة: {breach.get_severity_display()}"
    if breach.ncsa_deadline:
        body += f" — مهلةُ إشعار الجهة المختصّة حتى {timezone.localtime(breach.ncsa_deadline):%Y/%m/%d %H:%M}"
    body += ". افتح البلاغ لاتّخاذ الإجراء."
    try:
        from notifications.hub import NotificationHub

        with transaction.atomic():
            NotificationHub.dispatch(
                event_type="breach_assigned",
                school=breach.school,
                recipients=[assignee],
                title=ASSIGNED_TITLE,
                body=body,
                related_url=f"/breach/{breach.pk}/",
                related_object_id=str(breach.pk),
                sent_by=by,
            )
    except Exception:  # noqa: BLE001 — الإشعارُ لا يُسقط تسجيلَ خرقٍ عليه مهلةُ 72 ساعة
        logger.error("breach assignee notification failed breach=%s", breach.pk, exc_info=True)
        return False
    return True


def register_breach(*, form, user, school, request=None) -> BreachReport:
    breach = form.save(commit=False)
    breach.school = school
    breach.reported_by = user
    breach.save()
    if not breach.notification_text.strip():
        breach.notification_text = build_ncsa_text(breach)
        breach.save(update_fields=["notification_text"])
    AuditLog.log(
        user=user,
        action="create",
        model_name="other",
        object_id=str(breach.pk),
        object_repr=f"BreachReport: {breach.title}",
        school=school,
        request=request,
    )
    notify_assignee(breach, assignee=breach.assigned_to if breach.assigned_to_id else None, by=user)
    return breach


#: الحدُّ الأدنى لإشعارٍ «مكتمل» (مواصفة 0104): ما يذكره نصُّ الإشعار نفسُه. وما نقص فإشعارٌ مبدئيٌّ بأسباب النقص.
_NCSA_MINIMUM = (
    ("notification_text", "نصّ الإشعار"),
    ("immediate_action", "الإجراء الفوري"),
    ("containment_action", "إجراءات الاحتواء"),
)


def ncsa_minimum_gaps(breach: BreachReport) -> list[str]:
    """الحقولُ الناقصةُ للحدّ الأدنى لإشعار NCSA المكتمل (فارغٌ = مستوفى)."""
    gaps = [label for name, label in _NCSA_MINIMUM if not (getattr(breach, name) or "").strip()]
    if not breach.affected_count:
        gaps.append("عدد المتأثرين")
    return gaps


def _assert_complete_allowed(breach: BreachReport) -> None:
    gaps = ncsa_minimum_gaps(breach)
    if gaps:
        raise InvalidTransitionError(
            "لا يُسجَّل إشعارٌ مكتمل وينقصه: " + "، ".join(gaps) + ". استكملها أو سجّله إشعاراً مبدئيّاً."
        )


def _assert_can_resolve(breach: BreachReport) -> None:
    """لا يُغلق خرقٌ ما زال عليه التزامٌ معلَنٌ لم يُوفَّ: إشعارٌ مبدئيٌّ لم يكتمل، أو أفرادٌ واجبٌ إخطارُهم."""
    if breach.ncsa_notice_stage == "initial":
        raise InvalidTransitionError("لا يُغلق الخرقُ وإشعارُ NCSA المبدئيُّ لم يكتمل — استكمله أوّلاً.")
    if breach.individuals_status == "not_assessed" and (
        breach.severity in ("high", "critical") or breach.affected_count > 0
    ):
        raise InvalidTransitionError(
            "تقديرُ إخطار الأفراد واجبٌ قبل إغلاق خرقٍ شدّته عالية أو فيه متأثّرون (م.14) — "
            "سجّل التقدير: واجبٌ بموعد، أو غيرُ لازمٍ بسببٍ مكتوب."
        )
    if breach.individuals_status == "required":
        raise InvalidTransitionError(
            "لا يُغلق الخرقُ والأفرادُ المتأثّرون واجبٌ إخطارُهم ولم يُخطَروا — سجّل الإخطارَ أو أعد التقييم."
        )


def transition(breach: BreachReport, new_status: str, *, user, request=None) -> BreachReport:
    """ينقل الخرقَ إلى `new_status`. مُتماثِلُ الأثر: الحالةُ الحاليّةُ لا تغيّر شيئاً."""
    labels = dict(BreachReport.STATUS)
    if new_status not in labels:
        raise InvalidTransitionError("حالةٌ غيرُ معروفة.")

    with transaction.atomic():
        locked = BreachReport.objects.select_for_update().get(pk=breach.pk)
        old_status = locked.status
        if new_status == old_status:
            return locked
        if new_status not in ALLOWED_TRANSITIONS[old_status]:
            raise InvalidTransitionError(
                f"لا يمكن الانتقال من «{labels[old_status]}» إلى «{labels[new_status]}»."
            )

        now = timezone.now()
        locked.status = new_status
        changes = {"from": old_status, "to": new_status}
        if new_status == "notified" and not locked.ncsa_notified_at:
            locked.ncsa_notified_at = now
            changes["ncsa_notified_at"] = now.isoformat()
            # المسارُ القديم (انتقالٌ مباشرٌ إلى «تم الإشعار») إشعارٌ مكتمل فيلزمه الحدُّ الأدنى؛ والمبدئيُّ له `record_ncsa_notice`.
            if locked.ncsa_notice_stage == "none":
                _assert_complete_allowed(locked)
                locked.ncsa_notice_stage = "complete"
                locked.ncsa_completed_at = now
                changes["ncsa_notice_stage"] = "complete"
        if new_status == "resolved":
            _assert_can_resolve(locked)
            locked.resolved_at = now
            if not locked.ncsa_notified_at:
                changes["closed_without_ncsa_notice"] = True
            if locked.individuals_status == "not_assessed":
                changes["closed_without_individuals_assessment"] = True
        locked.save()
        AuditLog.log(
            user=user,
            action="update",
            model_name="other",
            object_id=str(locked.pk),
            object_repr=f"BreachReport status: {labels[old_status]} → {labels[new_status]}",
            changes=changes,
            school=locked.school,
            request=request,
        )
    return locked


def update_breach(breach: BreachReport, form, *, user, request=None) -> BreachReport:
    """يحفظ تعديلَ خرقٍ مفتوح ويُدقّق الحقولَ المتغيّرة. الخرقُ المُغلق سجلٌّ لا يُعدَّل."""
    with transaction.atomic():
        locked = BreachReport.objects.select_for_update().get(pk=breach.pk)
        if locked.status == "resolved":
            raise InvalidTransitionError("لا يُعدَّل خرقٌ مُغلق.")
        previous_assignee_id = locked.assigned_to_id
        changed = list(form.changed_data)
        saved = form.save(commit=False)
        # النصُّ يُولَّد إن فُرغ أو طُلبت إعادتُه؛ وبعد «تم الإشعار» مقفلٌ فلا يمسّه شيء.
        regenerate = form.cleaned_data.get("regenerate_notice") and locked.status != "notified"
        if regenerate or not saved.notification_text.strip():
            saved.notification_text = build_ncsa_text(saved)
        # حقولُ النموذج وحدَها: النسخةُ المقروءةُ خارج القفل قديمةٌ فيما عداها (الحالةُ ومراحلُ الإشعار والإخطار).
        saved.save(update_fields=list(form._meta.fields))
        if changed:
            AuditLog.log(
                user=user,
                action="update",
                model_name="other",
                object_id=str(saved.pk),
                object_repr=f"BreachReport edit: {saved.title}",
                changes={"edited_fields": changed},
                school=saved.school,
                request=request,
            )
        # مرّةً لكلّ تغييرٍ في المكلَّف — المقارنةُ بما تحت القفل لا بما قرأه العرضُ، فتكرارُ إرسال النموذج نفسِه لا يُنبّه ثانيةً.
        if saved.assigned_to_id and saved.assigned_to_id != previous_assignee_id:
            notify_assignee(saved, assignee=saved.assigned_to, by=user)
    return saved


# ── إشعار NCSA على مراحل (W-20261002-007) ──────────────────────────────


def record_ncsa_notice(
    breach: BreachReport,
    *,
    complete: bool,
    missing_reasons: str = "",
    completion_due_at=None,
    user,
    request=None,
) -> BreachReport:
    """يسجّل إرسالَ إشعار NCSA الأوّل: مكتملاً، أو مبدئيّاً بأسباب النقص وموعد الاستكمال.

    وقتُ الإشعار (`ncsa_notified_at`) يُختم هنا مرّةً واحدة ويوقف احتسابَ المهلة (72 ساعة)؛
    والاستكمالُ اللاحق (`complete_ncsa_notice`) لا يمسّه. المبدئيُّ لا يصحّ بلا سببٍ وموعد.
    """
    reasons = (missing_reasons or "").strip()
    now = timezone.now()
    if complete:
        _assert_complete_allowed(breach)
    else:
        if not reasons:
            raise InvalidTransitionError("الإشعارُ المبدئيُّ يستلزم ذكرَ أسباب نقص المعلومات.")
        if completion_due_at is None or completion_due_at <= now:
            raise InvalidTransitionError("الإشعارُ المبدئيُّ يستلزم موعدَ استكمالٍ في المستقبل.")
    with transaction.atomic():
        locked = BreachReport.objects.select_for_update().get(pk=breach.pk)
        if locked.status not in ("discovered", "assessing"):
            raise InvalidTransitionError("سُجّل إشعارُ NCSA لهذا الخرق من قبلُ أو أُغلق.")
        old_status = locked.status
        locked.status = "notified"
        locked.ncsa_notified_at = now
        if complete:
            locked.ncsa_notice_stage = "complete"
            locked.ncsa_completed_at = now
        else:
            locked.ncsa_notice_stage = "initial"
            locked.ncsa_missing_reasons = reasons
            locked.ncsa_completion_due_at = completion_due_at
        locked.save()
        changes = {
            "from": old_status,
            "to": "notified",
            "ncsa_notified_at": now.isoformat(),
            "ncsa_notice_stage": locked.ncsa_notice_stage,
        }
        if not complete:
            changes["ncsa_completion_due_at"] = completion_due_at.isoformat()
        AuditLog.log(
            user=user,
            action="update",
            model_name="other",
            object_id=str(locked.pk),
            object_repr=f"BreachReport NCSA notice: {locked.get_ncsa_notice_stage_display()}",
            changes=changes,
            school=locked.school,
            request=request,
        )
    return locked


def complete_ncsa_notice(breach: BreachReport, *, user, request=None) -> BreachReport:
    """يسجّل استكمالَ إشعار NCSA المبدئي. لا يمسّ `ncsa_notified_at` فتبقى المهلةُ الأصليّة محسوبةً."""
    with transaction.atomic():
        locked = BreachReport.objects.select_for_update().get(pk=breach.pk)
        if locked.ncsa_notice_stage != "initial" or locked.status != "notified":
            raise InvalidTransitionError("لا إشعارَ مبدئيَّ مفتوحاً لهذا الخرق.")
        _assert_complete_allowed(locked)
        now = timezone.now()
        late = bool(locked.ncsa_completion_due_at and now > locked.ncsa_completion_due_at)
        locked.ncsa_notice_stage = "complete"
        locked.ncsa_completed_at = now
        locked.save(update_fields=["ncsa_notice_stage", "ncsa_completed_at"])
        AuditLog.log(
            user=user,
            action="update",
            model_name="other",
            object_id=str(locked.pk),
            object_repr="BreachReport NCSA notice: استُكمل",
            changes={
                "ncsa_notice_stage": "complete",
                "ncsa_completed_at": now.isoformat(),
                "completed_after_due": late,
            },
            school=locked.school,
            request=request,
        )
    return locked


# ── إخطار الأفراد المتأثّرين (W-20261002-006) ────────────────────────────


def assess_individuals(
    breach: BreachReport,
    *,
    required: bool,
    note: str,
    deadline=None,
    user,
    request=None,
) -> BreachReport:
    """يسجّل تقديرَ لزوم إخطار الأفراد: واجبٌ بموعد، أو غيرُ لازمٍ بسببٍ مكتوب (م.14).

    موعدُ الإخطار الافتراضيُّ = موعدُ إشعار NCSA (اكتشاف + 72 ساعة)؛ ويُعدَّل صراحةً ويُدقَّق.
    والتقديرُ يُعاد ما لم يُخطَر الأفراد فعلاً أو يُغلق الخرق.
    """
    note = (note or "").strip()
    if not required and not note:
        raise InvalidTransitionError("عدمُ لزوم إخطار الأفراد يستلزم ذكرَ السبب.")
    with transaction.atomic():
        locked = BreachReport.objects.select_for_update().get(pk=breach.pk)
        if locked.status == "resolved":
            raise InvalidTransitionError("لا يُعدَّل خرقٌ مُغلق.")
        if locked.individuals_status == "notified":
            raise InvalidTransitionError("أُخطر الأفرادُ فعلاً ولا يُعاد التقدير.")
        old = locked.individuals_status
        if required:
            locked.individuals_status = "required"
            locked.individuals_deadline = deadline or locked.ncsa_deadline
        else:
            locked.individuals_status = "not_required"
            locked.individuals_deadline = None
        locked.individuals_assessed_at = timezone.now()
        locked.individuals_assessment_note = note
        locked.individuals_decided_by = user
        locked.save(
            update_fields=[
                "individuals_status",
                "individuals_deadline",
                "individuals_assessed_at",
                "individuals_assessment_note",
                "individuals_decided_by",
            ]
        )
        AuditLog.log(
            user=user,
            action="update",
            model_name="other",
            object_id=str(locked.pk),
            object_repr=f"BreachReport individuals: {locked.get_individuals_status_display()}",
            changes={
                "individuals_status_from": old,
                "individuals_status": locked.individuals_status,
                "individuals_deadline": (
                    locked.individuals_deadline.isoformat() if locked.individuals_deadline else None
                ),
            },
            school=locked.school,
            request=request,
        )
    return locked


def record_individuals_notified(
    breach: BreachReport, *, channel: str, user, request=None
) -> BreachReport:
    """يختم وقتَ إخطار الأفراد الفعليَّ وقناتَه مرّةً واحدة (لا رجعة)، ويدقّق التأخّرَ عن الموعد."""
    if channel not in dict(BreachReport.INDIVIDUALS_CHANNELS):
        raise InvalidTransitionError("اختر قناةَ إخطار الأفراد.")
    with transaction.atomic():
        locked = BreachReport.objects.select_for_update().get(pk=breach.pk)
        if locked.status == "resolved":
            raise InvalidTransitionError("لا يُعدَّل خرقٌ مُغلق.")
        if locked.individuals_status != "required":
            raise InvalidTransitionError("لا يُسجَّل إخطارٌ إلا للأفراد الذين قُدِّر وجوبُ إخطارهم.")
        now = timezone.now()
        late = bool(locked.individuals_deadline and now > locked.individuals_deadline)
        locked.individuals_status = "notified"
        locked.individuals_notified_at = now
        locked.individuals_notified_channel = channel
        locked.save(
            update_fields=[
                "individuals_status",
                "individuals_notified_at",
                "individuals_notified_channel",
            ]
        )
        AuditLog.log(
            user=user,
            action="update",
            model_name="other",
            object_id=str(locked.pk),
            object_repr="BreachReport individuals: أُخطروا",
            changes={
                "individuals_status_from": "required",
                "individuals_status": "notified",
                "individuals_notified_at": now.isoformat(),
                "individuals_notified_channel": channel,
                "notified_after_deadline": late,
            },
            school=locked.school,
            request=request,
        )
    return locked

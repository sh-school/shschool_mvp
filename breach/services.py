"""breach/services.py — تسجيلُ الخرق وانتقالاتُ حالته (PDPPL م.11 + NCSA 72h).

وقتُ إشعار NCSA (`ncsa_notified_at`) هو المعتمَد قانونيّاً في احتساب الالتزام بالمهلة؛
فيُختم مرّةً واحدةً تحت قفلِ الصفّ، وكلُّ انتقالٍ يُدقَّق في `AuditLog`.
"""

from django.db import transaction
from django.utils import timezone

from core.models import AuditLog, BreachReport

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
    return breach


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
        if new_status == "resolved":
            locked.resolved_at = now
            if not locked.ncsa_notified_at:
                changes["closed_without_ncsa_notice"] = True
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
        changed = list(form.changed_data)
        saved = form.save(commit=False)
        # النصُّ يُولَّد إن فُرغ أو طُلبت إعادتُه؛ وبعد «تم الإشعار» مقفلٌ فلا يمسّه شيء.
        regenerate = form.cleaned_data.get("regenerate_notice") and locked.status != "notified"
        if regenerate or not saved.notification_text.strip():
            saved.notification_text = build_ncsa_text(saved)
        saved.save()
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
    return saved

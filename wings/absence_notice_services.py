"""إخطارُ وليّ الأمر بالغياب يُصدره **حاصرُ الغياب بنفسه** بعد ح4 (قرارُ المالك D-246م) — لا يُرسَل شيءٌ لوليّ الأمر تلقائياً من أيّ مسار.

التنبيهاتُ تُنشأ «محجوزةً» (`held`) من المسح والمسارَين القدامى؛ وهذا الجزءُ وحدَه يحوّل المحجوزَ إلى إخطار. الضماناتُ كلُّها على الخادم:

- الدورُ: `admin_supervisor` مع `wings.school_wide` (`holds_school_wide`) — غيرُه ممنوع.
- التوقيتُ: لا إصدارَ لتنبيهِ اليوم قبل انتهاء ح4 بجرس صفّ الطالب (التنبيهُ من يومٍ سابقٍ مسموح).
- المستلم: من روابط وليّ الأمر المسجَّلة (`ParentStudentLink` عبر الـHub) لا من الطلب.
- لا إخطارَ مزدوج: مطالبةٌ ذرّيّةٌ `UPDATE … WHERE status='held'` فيمضي طلبٌ واحد؛ ومن يخسر السباق يُرفض. ولا إخطارَ لمن صُحّح غيابُه (لم تعد العتبةُ مستحقّة): يُوسَم `resolved` بلا إرسال.
- حالةٌ وسيطةٌ خاصّة `issuing` أثناء الإرسال لا يلتقطها المرسِلُ الجماعيّ (07:00 والزرّ اليدويّ يلتقطان `pending` وحدَه)؛ فتوقّفُ العملية بين المطالبة والنهاية (إعادةُ نشر) لا يُخرج إخطاراً ثانياً بمسارٍ غير الزرّ.
  وما علق فيها أكثرَ من `STUCK_MINUTES` يعيده `reconcile_stuck` إلى `held` (الزمنُ من سطر تدقيق المطالبة).
- الفشلُ يُعيد الحالةَ إلى `held` لا `pending` — فلا يخرج إخطارٌ بلا كاتب.
- التدقيقُ بمعرّفاتٍ وعتبةٍ فقط، بلا اسمِ طالبٍ ولا وليّ.
"""

from __future__ import annotations

import datetime as dt
import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

from django.db import transaction
from django.utils import timezone

from core.models import AuditLog
from core.parents_freeze import parents_frozen

if TYPE_CHECKING:
    from core.models import CustomUser, School

logger = logging.getLogger(__name__)

PERIOD_BOUND = 4  # يُصدر الإخطارَ بعد انتهاء الحصّة الرابعة
AUDIT_LABEL = "إخطارُ غياب — حاصرُ الغياب"
STUCK_MINUTES = 15  # أقصى مُكثٍ لتنبيهٍ في «قيد الإصدار» قبل أن يُعاد إلى «محجوز»


class IssueRefused(Exception):  # noqa: N818 — رفضٌ بمعنى لا عطل
    """رفضٌ برسالةٍ للكاتب."""


@dataclass(frozen=True)
class IssueResult:
    status: str  # sent | resolved
    message: str


def held_alerts(school: School):
    from operations.models import AbsenceAlert

    return AbsenceAlert.objects.filter(school=school, status="held").select_related("student")


def held_count(school: School) -> int:
    return held_alerts(school).count()


def reconcile_stuck(school: School, *, now: dt.datetime | None = None) -> int:
    """يعيد إلى «محجوز» كلَّ تنبيهٍ علق في «قيد الإصدار» أكثرَ من `STUCK_MINUTES` (انقطعت العمليةُ بين المطالبة والنهاية). يعيد عددَ ما أُعيد.

    الزمنُ من سطر تدقيق المطالبة؛ ولا سطرَ ← يُعاد فوراً. لا يرسل شيئاً: يُرجِع الحالةَ فقط.
    """
    from operations.models import AbsenceAlert

    cutoff = (now or timezone.now()) - dt.timedelta(minutes=STUCK_MINUTES)
    released = 0
    for alert in AbsenceAlert.objects.filter(school=school, status="issuing"):
        claim = (
            AuditLog.objects.filter(
                object_id=str(alert.pk), object_repr=AUDIT_LABEL, changes__action="issuing"
            )
            .order_by("-timestamp")
            .first()
        )
        if claim is not None and claim.timestamp > cutoff:
            continue
        if AbsenceAlert.objects.filter(pk=alert.pk, status="issuing").update(status="held"):
            _audit(None, school, alert, "released_stuck")
            released += 1
    return released


def screen_rows(school: School) -> list[dict]:
    """صفوفُ شاشة المحجوزات: التنبيه وتسميةُ عتبته المقروءة (لا مفتاحُها الخام). تُصالح العالقَ أولاً."""
    from operations.absence_policy import GATES_1_11

    reconcile_stuck(school)
    labels = {g.key: g.label for g in GATES_1_11}
    return [
        {"alert": alert, "label": labels.get(alert.gate, alert.gate)}
        for alert in held_alerts(school)
    ]


def period_four_over(alert, now: dt.datetime) -> bool:
    """أانتهت ح4 بجرس صفّ الطالب اليوم؟ تنبيهٌ أُنشئ في يومٍ سابقٍ يُصدَر في أيّ وقت."""
    from core.models import StudentEnrollment
    from operations.models import TimeSlotConfig
    from operations.school_days import school_day

    today = timezone.localtime(now).date()
    if timezone.localtime(alert.created_at).date() < today:
        return True
    enrollment = StudentEnrollment.objects.current_of(alert.student)
    if enrollment is None:
        return False
    klass = enrollment.class_group
    day_type = school_day(alert.school, today).bell_day_type
    if not day_type or klass.time_band_id is None:
        return False  # لا جرسَ معرَّف لصفّه اليوم: لا إصدارَ حتى يُعرَّف
    row = TimeSlotConfig.objects.filter(
        school=alert.school,
        band_id=klass.time_band_id,
        day_type=day_type,
        is_break=False,
        period_number=PERIOD_BOUND,
    ).first()
    if row is None:
        return False  # لا ح4 في جرس صفّه
    return timezone.localtime(now).time() >= row.end_time


def _still_due(alert, today: dt.date) -> tuple[bool, object, int]:
    """أما زالت العتبةُ مستحقّةً الآن؟ (إعادةُ حسابٍ — غيابٌ صُحّح لا يُخطَر به)."""
    from core.models import StudentEnrollment
    from operations.absence_policy import gates_for
    from operations.absence_standing import standing_for
    from operations.attendance_policy import is_special_education
    from operations.services import AttendanceService

    enrollment = StudentEnrollment.objects.current_of(alert.student)
    grade = enrollment.class_group.grade if enrollment else None
    ese = bool(enrollment and is_special_education(enrollment.class_group))  # D-255م
    if not gates_for(grade, ese):
        return False, None, 0
    standing = standing_for(alert.student, alert.school, grade=grade, on=today, ese=ese)
    margin = AttendanceService.GATE_WARNING_MARGIN_DAYS
    for gate in standing.gates:
        if gate.key != alert.gate:
            continue
        due = (
            standing.unexcused_days > gate.max_days
            or gate.max_days - standing.unexcused_days <= margin
        )
        return due, gate, standing.unexcused_days
    return False, None, 0


def issue(
    user: CustomUser, school: School, alert_id, *, now: dt.datetime | None = None
) -> IssueResult:
    """يُصدر إخطارَ وليّ الأمر لتنبيهٍ محجوز. يرفع `IssueRefused` برسالةٍ، أو يعيد (أُرسل | حُلّ بلا إرسال)."""
    from notifications.hub import NotificationHub
    from operations.models import AbsenceAlert
    from operations.services.attendance import NEWLINE, absence_notice_text
    from wings.services import holds_school_wide

    if not holds_school_wide(user):
        raise IssueRefused("الإصدارُ لحاصر الغياب العامّ وحدَه")
    if parents_frozen():
        # قبل أيّ مطالبةٍ أو تغييرِ حالة: التنبيهُ يبقى «محجوزاً» كما هو فيُصدَر عند الفكّ (W-20261008-013).
        raise IssueRefused(
            "التواصل مع أولياء الأمور مجمَّد — لا يُصدَر إخطارٌ الآن، ويبقى التنبيهُ محجوزاً"
        )
    now = now or timezone.now()
    try:
        alert = AbsenceAlert.objects.select_related("student", "school").get(
            pk=alert_id, school=school
        )
    except (AbsenceAlert.DoesNotExist, ValueError, TypeError):
        raise IssueRefused("التنبيه غيرُ موجود") from None
    if alert.status != "held":
        raise IssueRefused("لم يعد هذا التنبيهُ بانتظار الإصدار")
    if not period_four_over(alert, now):
        raise IssueRefused("يُصدَر الإخطارُ بعد انتهاء الحصّة الرابعة")

    due, gate, days = _still_due(alert, timezone.localtime(now).date())
    if not due:
        AbsenceAlert.objects.filter(pk=alert.pk, status="held").update(
            status="resolved", resolved_by=user
        )
        _audit(user, school, alert, "resolved_before_issue")
        return IssueResult("resolved", "صُحّح الغيابُ فلم تعد العتبةُ مستحقّةً — لم يُرسَل إخطار")

    # مطالبةٌ ذرّيّة: طلبٌ واحدٌ فقط يمضي
    # المطالبةُ وسطرُ تدقيقها في معاملةٍ واحدة: لا نافذةَ يرى فيها المصالِحُ «issuing» بلا سطر مطالبةٍ فيعيده وهو قيد الإرسال (ملاحظة 0104 P3)
    with transaction.atomic():
        claimed = AbsenceAlert.objects.filter(pk=alert.pk, status="held").update(status="issuing")
        if not claimed:
            raise IssueRefused("سبقك طلبٌ آخرُ إلى إصدار هذا الإخطار")
        _audit(user, school, alert, "issuing")

    _crossed, headline, detail, source = absence_notice_text(gate, days)
    try:
        NotificationHub.dispatch_to_parents(
            event_type="absence",
            school=school,
            student=alert.student,
            title=f"⚠️ {headline} — {alert.student.full_name}",
            body=NEWLINE.join([detail, source, "يُرجى التواصل مع المدرسة."]),
            context={"student": alert.student, "absence_count": days},
            related_url=f"/student-affairs/student/{alert.student_id}/",
        )
    except Exception:  # noqa: BLE001
        logger.exception("absence notice dispatch failed [alert=%s]", alert.pk)
        # الفشلُ يرجع إلى «محجوز» لا «معلَّق»: لا يلتقطه مرسِلُ 07:00 ولا يخرج إخطارٌ بلا كاتب (D-246م)
        AbsenceAlert.objects.filter(pk=alert.pk, status="issuing").update(status="held")
        _audit(user, school, alert, "issue_failed")
        raise IssueRefused("تعذّر الإرسال — بقي التنبيهُ محجوزاً فأعد المحاولة") from None

    AbsenceAlert.objects.filter(pk=alert.pk, status="issuing").update(
        status="notified", resolved_by=user
    )
    _audit(user, school, alert, "issued")
    return IssueResult("sent", "أُرسل الإخطارُ إلى وليّ الأمر")


def issue_message(user: CustomUser, school: School, alert_id) -> tuple[bool, str]:
    """للعرض: `(نجح؟، الرسالة)` — يلتقط الرفضَ برسالته فلا يحمل العرضُ منطقاً ولا يلمس الـORM (سقّاطة الطبقات)."""
    try:
        result = issue(user, school, alert_id)
    except IssueRefused as refusal:
        return False, str(refusal)
    return True, result.message


def _audit(user, school, alert, action: str) -> None:
    AuditLog.log(
        user=user,
        action="update",
        model_name="other",
        object_id=alert.pk,
        object_repr=AUDIT_LABEL,
        changes={"action": action, "gate": alert.gate, "count": alert.absence_count},
        school=school,
    )

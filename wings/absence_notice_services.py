"""إخطارُ وليّ الأمر بالغياب يُصدره **حاصرُ الغياب بنفسه** بعد ح4 (قرارُ المالك D-246م) — لا يُرسَل شيءٌ لوليّ الأمر تلقائياً من أيّ مسار.

التنبيهاتُ تُنشأ «محجوزةً» (`held`) من المسح والمسارَين القدامى؛ وهذا الجزءُ وحدَه يحوّل المحجوزَ إلى إخطار. الضماناتُ كلُّها على الخادم:

- الدورُ: `admin_supervisor` مع `wings.school_wide` (`holds_school_wide`) — غيرُه ممنوع.
- التوقيتُ: لا إصدارَ لتنبيهِ اليوم قبل انتهاء ح4 بجرس صفّ الطالب (التنبيهُ من يومٍ سابقٍ مسموح).
- المستلم: من روابط وليّ الأمر المسجَّلة (`ParentStudentLink` عبر الـHub) لا من الطلب.
- لا إخطارَ مزدوج: مطالبةٌ ذرّيّةٌ `UPDATE … WHERE status='held'` فيمضي طلبٌ واحد؛ ومن يخسر السباق يُرفض. ولا إخطارَ لمن صُحّح غيابُه (لم تعد العتبةُ مستحقّة): يُوسَم `resolved` بلا إرسال.
- الفشلُ يُعيد الحالةَ إلى `held` لا `pending` — فلا يلتقطه مرسِلُ 07:00 ولا يخرج إخطارٌ بلا كاتب.
- التدقيقُ بمعرّفاتٍ وعتبةٍ فقط، بلا اسمِ طالبٍ ولا وليّ.
"""

from __future__ import annotations

import datetime as dt
import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

from django.utils import timezone

from core.models import AuditLog

if TYPE_CHECKING:
    from core.models import CustomUser, School

logger = logging.getLogger(__name__)

PERIOD_BOUND = 4  # يُصدر الإخطارَ بعد انتهاء الحصّة الرابعة


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


def period_four_over(alert, now: dt.datetime) -> bool:
    """أانتهت ح4 بجرس صفّ الطالب اليوم؟ تنبيهٌ أُنشئ في يومٍ سابقٍ يُصدَر في أيّ وقت."""
    from core.models import StudentEnrollment
    from operations.services.provisional_session import _bell

    today = timezone.localtime(now).date()
    if timezone.localtime(alert.created_at).date() < today:
        return True
    enrollment = StudentEnrollment.objects.current_of(alert.student)
    if enrollment is None:
        return False
    times = _bell(alert.school, enrollment.class_group, today).get(PERIOD_BOUND)
    if times is None:
        return False  # لا ح4 في جرس صفّه: لا إصدارَ حتى يُعرَّف
    return timezone.localtime(now).time() >= times[1]


def _still_due(alert, today: dt.date) -> tuple[bool, object, int]:
    """أما زالت العتبةُ مستحقّةً الآن؟ (إعادةُ حسابٍ — غيابٌ صُحّح لا يُخطَر به)."""
    from core.models import StudentEnrollment
    from operations.absence_policy import gates_for
    from operations.absence_standing import standing_for
    from operations.services import AttendanceService

    enrollment = StudentEnrollment.objects.current_of(alert.student)
    grade = enrollment.class_group.grade if enrollment else None
    if not gates_for(grade):
        return False, None, 0
    standing = standing_for(alert.student, alert.school, grade=grade, on=today)
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
    claimed = AbsenceAlert.objects.filter(pk=alert.pk, status="held").update(status="pending")
    if not claimed:
        raise IssueRefused("سبقك طلبٌ آخرُ إلى إصدار هذا الإخطار")

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
        AbsenceAlert.objects.filter(pk=alert.pk, status="pending").update(status="held")
        raise IssueRefused("تعذّر الإرسال — بقي التنبيهُ محجوزاً فأعد المحاولة") from None

    AbsenceAlert.objects.filter(pk=alert.pk).update(status="notified", resolved_by=user)
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
        object_repr="إخطارُ غياب — حاصرُ الغياب",
        changes={"action": action, "gate": alert.gate, "count": alert.absence_count},
        school=school,
    )

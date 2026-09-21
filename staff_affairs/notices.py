"""إخطاراتُ الحضور والانصراف للموظّفين — سياسة ت/د 2027/01، البند 5.

«سيتم الخصم من الراتب بعد اشعار الموظف على البريد الالكتروني بداية كل شهر بتقرير أيام
الغياب عن الشهر السابق» (5.1)، و«يجب على الموظف تغطيه أيام غيابه قبل يوم (15) من الشهر
وإلا يتم تنفيذ الخصم» (5.3). فأوّلَ كلّ شهرٍ يُخطَر كلُّ موظّفٍ له يومُ غيابٍ **لم يُغطَّ**
(بلا نوعٍ من سجلّ الغياب ولا عذرٍ مقبول) داخلَ المنصّة، وبالبريد إن كان له بريدٌ.

والبريدُ يمرّ بمحرّك المنصّة نفسِه (``notifications.tasks.send_email_task``)، فيُسجَّل في
``NotificationLog`` ويُعاد ويُعزل عند الفشل. وفي الإنتاج اليومَ لا مزوّدَ بريدٍ مُهيَّأ
(``UndeliveredEmailBackend``) فيُسجَّل «لم يُسلَّم» ولا يُقال «أُرسل» — والإشعارُ داخل المنصّة
يصل دائماً. فإذا هُيّئ المزوّدُ (``EMAIL_HOST*`` على الخدمات الثلاث) جرى البريدُ بلا تعديل.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date

from django.db import transaction

from core.models.school import School
from core.models.user import CustomUser
from staff_affairs.attendance import COVERAGE_DEADLINE_DAY, month_bounds
from staff_affairs.models import StaffAttendance


def uncovered_absences(school: School, year: int, month: int) -> dict[CustomUser, list[date]]:
    """أيّامُ غيابٍ لم تُغطَّ في شهر ``year``-``month``، لكلّ موظّف — م-35: «قبل يوم 15»."""
    first, last = month_bounds(date(year, month, 1))
    rows = (
        StaffAttendance.objects.filter(
            school=school, date__range=(first, last), status="absent", absence_type=""
        )
        .select_related("staff")
        .order_by("staff__full_name", "date")
    )
    by_staff: dict[CustomUser, list[date]] = defaultdict(list)
    for record in rows:
        by_staff[record.staff].append(record.date)
    return dict(by_staff)


def _message(days: list[date], year: int, month: int) -> tuple[str, str]:
    """(العنوانُ، النصّ) — نصٌّ واحدٌ للمنصّة والبريد، بلا ذكرٍ لسبب الغياب (بيانةٌ صحّيّةٌ محتملة)."""
    listed = "، ".join(f"{d:%d/%m}" for d in days)
    subject = f"تقرير أيام الغياب عن شهر {month:02d}/{year}"
    body = (
        f"سُجّل عليك {len(days)} يومُ غيابٍ لم يُغطَّ في شهر {month:02d}/{year}: {listed}.\n"
        f"يجب تغطيةُ هذه الأيام (بإجازةٍ أو عذرٍ مقبول) قبل يوم {COVERAGE_DEADLINE_DAY + 1} من "
        "هذا الشهر، وإلّا نُفّذ الخصمُ من الراتب (سياسة الحضور والانصراف 5.1 و5.3)."
    )
    return subject, body


def send_monthly_absence_notices(school: School, year: int, month: int) -> int:
    """يُخطر كلَّ موظّفٍ له غيابٌ لم يُغطَّ عن الشهر — ويُرجع عددَ من أُخطروا.

    داخل المنصّة أوّلاً (لا يحتاج مزوّداً)، ثمّ البريدُ إن كان للموظّف بريد. ولا يُكرَّر:
    الإشعارُ الداخليّ مفتاحُه معرّفُ الشهر، فتشغيلُ المهمّة ثانيةً في اليوم نفسِه لا يُضاعفه.
    """
    from notifications.models import InAppNotification
    from notifications.tasks import send_email_task

    notified = 0
    for staff, days in uncovered_absences(school, year, month).items():
        subject, body = _message(days, year, month)
        key = f"absence-notice:{year:04d}-{month:02d}:{staff.pk}"
        _notification, created = InAppNotification.objects.get_or_create(
            user=staff,
            school=school,
            related_object_id=key,
            defaults={
                "title": subject,
                "body": body,
                "event_type": "absence",
                "related_url": "/staff-affairs/permits/mine/",
            },
        )
        if not created:
            continue
        notified += 1
        if staff.email:
            transaction.on_commit(
                lambda staff=staff, subject=subject, body=body: send_email_task.delay(
                    school_id=str(school.pk),
                    recipient_email=staff.email,
                    subject=subject,
                    body_text=body,
                    notif_type="custom",
                )
            )
    return notified

"""
operations/guardian_contact.py — إخطارُ وليّ الأمر بغياب ابنه، بضغطةٍ من المشرف.

الدليلُ التنظيميّ 2026 (م 3.4.1.5، ص30): تُخطر إدارةُ المدرسة وليَّ الأمر بالغياب
**في اليوم نفسِه** هاتفيّاً ونصّيّاً، «فإن لم يردّ خلال يومين حُسب الغيابُ بلا
عذر». وقرارُ 2026-09-13: المشرفُ يسجّل «اتّصلتُ بوليّ الأمر» بضغطةٍ مع نتيجة
الاتّصال (ردّ / لم يردّ / سيُحضر عذراً). وقرارُ 2026-09-14: مهلةُ العذر تُعدّ من عودة
الطالب لا من الإخطار — فالإخطارُ سجلٌّ لا يحرّك المهلة.

فالسجلُّ هنا حقيقةٌ تُكتب لا تُحذف: من اتّصل، ومتى، وعن أيّ يومِ غياب، وبمَ
أجاب وليُّ الأمر. ومنه يُعرف في الكشف من غاب أمس ولم يُخطَر أهلُه بعد.
"""

from __future__ import annotations

import datetime as dt

from django.utils import timezone

from core.models import ClassGroup, CustomUser, School
from operations.models import GuardianContact, Session, StudentAttendance


class ContactError(ValueError):
    """رُفض التسجيلُ — والرسالةُ للمستخدم."""


def log_contact(
    *,
    student: CustomUser,
    school: School,
    absence_date: dt.date,
    outcome: str,
    by: CustomUser,
    note: str = "",
    channel: str = "phone",
    now: dt.datetime | None = None,
) -> GuardianContact:
    """يسجّل إخطارَ وليّ الأمر عن يومِ غيابٍ بعينه — والنتيجةُ من الثلاث."""
    if outcome not in dict(GuardianContact.OUTCOMES):
        raise ContactError("نتيجةُ الاتّصال: ردّ، أو لم يردّ، أو سيُحضر عذراً.")
    if channel not in dict(GuardianContact.CHANNELS):
        channel = "phone"
    return GuardianContact.objects.create(
        school=school,
        student=student,
        absence_date=absence_date,
        outcome=outcome,
        note=(note or "").strip(),
        channel=channel,
        contacted_by=by,
        contacted_at=now or timezone.now(),
    )


def contacts_of(student: CustomUser, school: School, limit: int = 20) -> list[GuardianContact]:
    return list(
        GuardianContact.objects.filter(student=student, school=school)
        .select_related("contacted_by")
        .order_by("-contacted_at")[:limit]
    )


def awaiting_contact(class_group: ClassGroup, day: dt.date) -> dict:
    """من غاب في آخر يومٍ دراسيٍّ قبل `day` ولم يُخطَر وليُّ أمره عنه: `{student_id: date}`.

    الغيابُ المعتبَر ما ثبّته الرصدُ «غائباً» بلا عذر؛ ومن أُخطر أهلُه عن ذلك اليوم
    يخرج من القائمة — نتيجةُ الاتّصال لا تهمّ هنا، فـ«لم يردّ» إخطارٌ أيضاً.
    """
    last = (
        Session.objects.filter(class_group=class_group, date__lt=day)
        .exclude(status="cancelled")
        .order_by("-date")
        .values_list("date", flat=True)
        .first()
    )
    if last is None:
        return {}
    absent = set(
        StudentAttendance.objects.filter(
            session__class_group=class_group,
            session__date=last,
            status="absent",
            excuse_type="",
        ).values_list("student_id", flat=True)
    )
    if not absent:
        return {}
    contacted = set(
        GuardianContact.objects.filter(
            student_id__in=absent, absence_date=last, school=class_group.school
        ).values_list("student_id", flat=True)
    )
    return {sid: last for sid in absent - contacted}

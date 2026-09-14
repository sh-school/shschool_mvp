"""
operations/excuses.py — تحويلُ الغياب «بلا عذر» إلى «بعذرٍ مقبول» (قرارُ 2026-09-13).

الدليلُ التنظيميّ 2026:

- **م 3.4.1.4 (ص29)**: الأعذارُ المقبولةُ **خمسةٌ بقائمةٍ مغلقة** — مرضٌ بتقريرٍ طبّيّ
  (خلال يومين من العودة)، ووفاةٌ في القرابة الأولى، وظرفٌ عائليٌّ طارئٌ بكتابٍ
  رسميّ، وتمثيلُ الدولة في لقاءٍ خارجيّ، ومواعيدُ المحاكم والهيئات (ومقابلاتُ
  الثاني عشر). «وكلُّ ما عدا ذلك غيابٌ بدون عذر».
- **م 3.4.1.5 (ص30)**: تُخطر المدرسةُ وليَّ الأمر في اليوم نفسِه، «فإن لم يردّ خلال
  **يومين** حُسب الغيابُ بلا عذر».

فالقاعدةُ هنا: **المشرفُ** يقبل العذرَ في مهلة يومين من آخر يومِ غياب، و**النائبُ
الإداريّ** وحدَه يقبله بعدها بسببٍ مكتوب (قدرةُ `wings.excuse_after_deadline`).
والمستندُ شرطٌ حيث اشترطه النصّ، وعذرُ الوفاة ببيان القرابة.

القرارُ واحدٌ (`AbsenceExcuse`) يغطّي كلَّ حصص الغياب بلا عذرٍ في مدّته، ويُكتب
نوعُه على كلّ صفٍّ لأنّ `absence_standing` يقرأ `excuse_type` — فيُسقط العذرُ
اليومَ من عدّ الحرمان (س12 = نعم). وإلغاؤه يُعيد الصفوفَ «بلا عذر»، وكلاهما في
سجلّ المراجعة.
"""

from __future__ import annotations

import datetime as dt

from django.core.files.uploadedfile import UploadedFile
from django.db import transaction
from django.utils import timezone

from core.models import AuditLog, CustomUser, School
from core.validators import FileTypeValidator
from operations.bells import day_type_for
from operations.models import AbsenceExcuse, StudentAttendance

#: القائمةُ المغلقة — بترتيب النصّ.
CLOSED_LIST = ("medical", "bereavement", "family", "state_representation", "official")

#: ما يشترط النصُّ مستندَه — والوفاةُ ببيانٍ لا بمستند.
NEEDS_DOCUMENT = {
    "medical": "التقريرُ الطبّيّ",
    "family": "الكتابُ الرسميّ",
    "state_representation": "خطابُ الجهة",
    "official": "إثباتُ الموعد",
}

#: مهلةُ الردّ: يومان **دراسيّان** (م 3.4.1.5، وقرارُ 2026-09-14: دراسيّاً لا تقويميّاً)،
#: تُعدّ من آخر يومِ غياب — فالجمعةُ والسبتُ والإجازاتُ لا تُحسب على وليّ الأمر.
GRACE_DAYS = 2


class ExcuseError(ValueError):
    """رُفض العذرُ — والرسالةُ للمستخدم."""


def kinds() -> list[tuple[str, str, str]]:
    """(المفتاح، الاسم، المستندُ المطلوب أو فارغ) — لبناء القائمة في الشاشة."""
    labels = dict(StudentAttendance.EXCUSE)
    return [(k, labels[k], NEEDS_DOCUMENT.get(k, "")) for k in CLOSED_LIST]


def is_school_day(school: School, day: dt.date) -> bool:
    """يومٌ يدرس فيه الطلبة: أحدٌ إلى خميس، وليس في إجازةٍ من تقويم الوزارة."""
    from core.models import CalendarEvent

    if not day_type_for(day):
        return False
    return not CalendarEvent.objects.filter(
        academic_year__school=school,
        event_type="break",
        audience__in=("both", "students"),
        start_date__lte=day,
        end_date__gte=day,
    ).exists()


def deadline_of(
    school: School,
    date_to: dt.date,
    *,
    student: CustomUser | None = None,
    date_from: dt.date | None = None,
) -> dt.date:
    """آخرُ يومٍ يُقبل فيه العذرُ عند المشرف: ثاني يومٍ دراسيٍّ بعد **الإخطار**.

    الإخطارُ يومُ آخر اتّصالٍ بوليّ الأمر عن غيابٍ في المدّة (قرارُ 2026-09-13:
    «مهلةُ اليومين تبدأ من الإخطار»)، ولا يسبق آخرَ يومِ غياب. ومن لم يُخطَر أهلُه
    تُعدّ مهلتُه من آخر يومِ غياب — فلا يُحاسَب وليُّ الأمر على ما لم يعلم به أشدَّ
    ممّن أُخطر.
    """
    base = date_to
    if student is not None:
        from operations.guardian_contact import last_notified_on

        notified = last_notified_on(student, school, date_from or date_to, date_to)
        if notified is not None and notified > base:
            base = notified
    day, counted = base, 0
    while counted < GRACE_DAYS:
        day += dt.timedelta(days=1)
        if is_school_day(school, day):
            counted += 1
    return day


def is_after_deadline(
    school: School,
    date_to: dt.date,
    today: dt.date,
    *,
    student: CustomUser | None = None,
    date_from: dt.date | None = None,
) -> bool:
    return today > deadline_of(school, date_to, student=student, date_from=date_from)


def _audit(
    by: CustomUser,
    school: School,
    action: str,
    excuse: AbsenceExcuse,
    changes: dict,
    *,
    ip: str | None = None,
) -> None:
    AuditLog.objects.create(
        user=by,
        school=school,
        action=action,
        model_name="other",
        object_id=str(excuse.pk),
        object_repr=f"عذرُ غياب: {excuse}"[:300],
        changes=changes,
        ip_address=ip,
    )


@transaction.atomic
def grant_excuse(
    *,
    student: CustomUser,
    school: School,
    date_from: dt.date,
    date_to: dt.date,
    kind: str,
    notes: str = "",
    document: UploadedFile | None = None,
    by: CustomUser,
    today: dt.date | None = None,
    may_override: bool = False,
    override_reason: str = "",
    ip: str | None = None,
) -> AbsenceExcuse:
    """يقبل عذراً من القائمة المغلقة لغياب `student` بين التاريخين — ويكتبه على صفوفه.

    يرفع `ExcuseError` برسالةٍ للمستخدم إن خالف القائمةَ أو المستندَ أو المهلةَ أو
    لم يجد غياباً بلا عذرٍ في المدّة.
    """
    today = today or timezone.localdate()
    notes = (notes or "").strip()
    override_reason = (override_reason or "").strip()

    if kind not in CLOSED_LIST:
        raise ExcuseError("العذرُ من القائمة المغلقة في الدليل (م 3.4.1.4) وحدَها.")
    if date_from > date_to:
        raise ExcuseError("تاريخُ البداية بعد النهاية.")
    if kind in NEEDS_DOCUMENT and not document:
        raise ExcuseError(f"{NEEDS_DOCUMENT[kind]} مطلوبٌ لهذا العذر.")
    if kind == "bereavement" and not notes:
        raise ExcuseError("اكتب صلةَ القرابة (الدرجةُ الأولى وحدَها).")
    if document:
        # النوعُ والحجمُ كما على حقل النموذج — `create` لا يشغّل المدقّقات وحدَه.
        FileTypeValidator(allowed_types="excuse", max_size_mb=10)(document)  # type: ignore[no-untyped-call]

    rows = StudentAttendance.objects.filter(
        student=student,
        school=school,
        status="absent",
        excuse_type="",
        session__date__gte=date_from,
        session__date__lte=date_to,
    )
    if not rows.exists():
        raise ExcuseError("لا غيابَ بلا عذرٍ لهذا الطالب في هذه المدّة.")

    late = is_after_deadline(school, date_to, today, student=student, date_from=date_from)
    if late and not may_override:
        closed = deadline_of(school, date_to, student=student, date_from=date_from)
        raise ExcuseError(
            f"انقضت مهلةُ اليومين الدراسيّين (حتى {closed:%d/%m}) — يقبله النائبُ الإداريّ بسبب."
        )
    if late and not override_reason:
        raise ExcuseError("اكتب سببَ القبول بعد المهلة.")

    excuse = AbsenceExcuse.objects.create(
        school=school,
        student=student,
        date_from=date_from,
        date_to=date_to,
        kind=kind,
        notes=notes,
        document=document,
        granted_by=by,
        after_deadline=late,
        override_reason=override_reason if late else "",
    )
    covered = rows.update(excuse=excuse, excuse_type=kind)
    _audit(
        by,
        school,
        "create",
        excuse,
        {
            "kind": kind,
            "from": date_from.isoformat(),
            "to": date_to.isoformat(),
            "rows": covered,
            "after_deadline": late,
            "override_reason": override_reason if late else "",
            "document": bool(document),
        },
        ip=ip,
    )
    return excuse


@transaction.atomic
def revoke_excuse(
    excuse: AbsenceExcuse, *, by: CustomUser, reason: str, ip: str | None = None
) -> int:
    """يُلغي العذرَ ويُعيد صفوفَه «بلا عذر» — بسببٍ في سجلّ المراجعة. يُعيد عددَ الصفوف."""
    reason = (reason or "").strip()
    if not reason:
        raise ExcuseError("اكتب سببَ الإلغاء.")
    restored = excuse.rows.update(excuse=None, excuse_type="")
    _audit(
        by,
        excuse.school,
        "delete",
        excuse,
        {
            "reason": reason,
            "kind": excuse.kind,
            "from": excuse.date_from.isoformat(),
            "to": excuse.date_to.isoformat(),
            "rows": restored,
        },
        ip=ip,
    )
    excuse.delete()
    return restored

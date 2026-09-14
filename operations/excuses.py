"""
operations/excuses.py — تحويلُ الغياب «بلا عذر» إلى «بعذرٍ مقبول».

الدليلُ التنظيميّ 2026:

- **م 3.4.1.4 (ص29)**: الأعذارُ المقبولةُ **خمسةٌ بقائمةٍ مغلقة** — مرضٌ بتقريرٍ طبّيّ
  (خلال يومين من العودة)، ووفاةٌ في القرابة الأولى، وظرفٌ عائليٌّ طارئٌ بكتابٍ
  رسميّ، وتمثيلُ الدولة في لقاءٍ خارجيّ، ومواعيدُ المحاكم والهيئات (ومقابلاتُ
  الثاني عشر). «وكلُّ ما عدا ذلك غيابٌ بدون عذر».

وقرارُ 2026-09-14: **المهلةُ يومان دراسيّان من عودة الطالب** لا من الإخطار — طالبٌ أُجريت
له عمليّةٌ فغاب أسبوعاً يُخطَر أهلُه في أوّل يوم، ويأتي العذرُ بعد عودته. فالمشرفُ يقبل
العذرَ ما دام الطالبُ لم يعد أو لم يمضِ يوما عودته، ومن بعدها **يرسله للنائب الإداريّ**
فيُحفظ «بانتظار النائب» حتى يقبله بسببٍ أو يرفضه بسبب (قدرةُ `wings.excuse_after_deadline`).

القرارُ واحدٌ (`AbsenceExcuse`) يغطّي كلَّ حصص الغياب بلا عذرٍ في مدّته، ويُكتب
نوعُه على كلّ صفٍّ لأنّ `absence_standing` يقرأ `excuse_type` — فيُسقط العذرُ
اليومَ من عدّ الحرمان. والصورةُ تُحفظ JPEG مصغّراً بلا بياناتٍ مخفيّة
(`core/photo_privacy.py`). وكلُّ قبولٍ ورفضٍ وإلغاءٍ في سجلّ المراجعة.
"""

from __future__ import annotations

import datetime as dt

from django.core.files.uploadedfile import UploadedFile
from django.db import transaction
from django.utils import timezone

from core.models import AuditLog, CustomUser, School
from core.photo_privacy import clean_photo
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

#: المهلةُ يومان **دراسيّان** بعد يوم عودة الطالب (قرارا 2026-09-14) — فالجمعةُ والسبتُ
#: وإجازاتُ تقويم الوزارة لا تُحسب على وليّ الأمر.
GRACE_DAYS = 2

#: ما يُعدّ عودةً: أوّلُ حصّةٍ حضرها بعد الغياب، ولو متأخّراً.
RETURNED = ("present", "late")


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


def return_day(school: School, student: CustomUser, after: dt.date) -> dt.date | None:
    """أوّلُ يومٍ حضر فيه الطالبُ بعد `after` — أو لا شيء إن لم يعد بعد."""
    day: dt.date | None = (
        StudentAttendance.objects.filter(
            student=student, school=school, session__date__gt=after, status__in=RETURNED
        )
        .order_by("session__date")
        .values_list("session__date", flat=True)
        .first()
    )
    return day


def deadline_of(school: School, student: CustomUser, date_to: dt.date) -> dt.date | None:
    """آخرُ يومٍ يقبل فيه المشرفُ العذر: ثاني يومٍ دراسيٍّ بعد عودة الطالب.

    ولا مهلةَ لمن لم يعد: يُعيد لا شيء، والعذرُ مقبولٌ عند المشرف حتى يعود ويمضي يوماه.
    """
    back = return_day(school, student, date_to)
    if back is None:
        return None
    day, counted = back, 0
    while counted < GRACE_DAYS:
        day += dt.timedelta(days=1)
        if is_school_day(school, day):
            counted += 1
    return day


def is_after_deadline(
    school: School, student: CustomUser, date_to: dt.date, today: dt.date
) -> bool:
    closed = deadline_of(school, student, date_to)
    return closed is not None and today > closed


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
    forward_if_late: bool = False,
    ip: str | None = None,
) -> AbsenceExcuse:
    """يقبل عذراً من القائمة المغلقة لغياب `student` بين التاريخين — ويكتبه على صفوفه.

    وبعد المهلة: من يملك القبولَ بعدها (`may_override`) يقبله بسبب، ومن لا يملكه يُحفظ
    عذرُه «بانتظار النائب» إن طلب ذلك (`forward_if_late`) — ولا يمسّ الصفوف.

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
        # والصورةُ تُحفظ JPEG مصغّراً بلا إحداثيّاتٍ ولا تاريخٍ ولا جهاز.
        document = clean_photo(document)  # type: ignore[assignment]

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

    late = is_after_deadline(school, student, date_to, today)
    forward = late and not may_override
    if forward and not forward_if_late:
        closed = deadline_of(school, student, date_to)
        raise ExcuseError(
            f"انقضت مهلةُ اليومين من عودة الطالب (حتى {closed:%d/%m}) — أرسله للنائب الإداريّ."
        )
    if forward and _awaiting_vice(student, school, date_from, date_to):
        raise ExcuseError("عذرٌ لهذه المدّة ينتظر النائبَ الإداريّ فعلاً.")
    if late and not forward and not override_reason:
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
        status="pending" if forward else "accepted",
        after_deadline=late,
        override_reason=override_reason if late and not forward else "",
    )
    covered = 0 if forward else rows.update(excuse=excuse, excuse_type=kind)
    _audit(
        by,
        school,
        "create",
        excuse,
        {
            "kind": kind,
            "status": excuse.status,
            "from": date_from.isoformat(),
            "to": date_to.isoformat(),
            "rows": covered,
            "after_deadline": late,
            "override_reason": excuse.override_reason,
            "document": bool(document),
        },
        ip=ip,
    )
    return excuse


def _awaiting_vice(
    student: CustomUser, school: School, date_from: dt.date, date_to: dt.date
) -> bool:
    return AbsenceExcuse.objects.filter(
        student=student,
        school=school,
        status="pending",
        date_from__lte=date_to,
        date_to__gte=date_from,
    ).exists()


def pending_for_vice(school: School) -> list[AbsenceExcuse]:
    """الأعذارُ المرسلةُ للنائب الإداريّ — الأقدمُ أوّلاً."""
    return list(
        AbsenceExcuse.objects.filter(school=school, status="pending")
        .select_related("student", "granted_by")
        .order_by("granted_at")
    )


@transaction.atomic
def approve_excuse(
    excuse: AbsenceExcuse, *, by: CustomUser, reason: str, ip: str | None = None
) -> int:
    """النائبُ يقبل عذراً أُرسل إليه — بسبب — فيُكتب على صفوفه. يُعيد عددَ الحصص."""
    reason = (reason or "").strip()
    if excuse.status != "pending":
        raise ExcuseError("هذا العذرُ ليس بانتظار النائب.")
    if not reason:
        raise ExcuseError("اكتب سببَ القبول بعد المهلة.")
    rows = StudentAttendance.objects.filter(
        student=excuse.student,
        school=excuse.school,
        status="absent",
        excuse_type="",
        session__date__gte=excuse.date_from,
        session__date__lte=excuse.date_to,
    )
    if not rows.exists():
        raise ExcuseError("لم يبقَ غيابٌ بلا عذرٍ في مدّة هذا العذر — ارفضه.")
    covered = rows.update(excuse=excuse, excuse_type=excuse.kind)
    excuse.status = "accepted"
    excuse.after_deadline = True
    excuse.override_reason = reason
    excuse.reviewed_by = by
    excuse.reviewed_at = timezone.now()
    excuse.save(
        update_fields=["status", "after_deadline", "override_reason", "reviewed_by", "reviewed_at"]
    )
    _audit(
        by,
        excuse.school,
        "update",
        excuse,
        {"decision": "accepted", "reason": reason, "rows": covered},
        ip=ip,
    )
    return covered


@transaction.atomic
def reject_excuse(
    excuse: AbsenceExcuse, *, by: CustomUser, reason: str, ip: str | None = None
) -> None:
    """النائبُ يرفض عذراً أُرسل إليه — بسبب. يبقى السجلُّ ومستندُه، والغيابُ بلا عذر."""
    reason = (reason or "").strip()
    if excuse.status != "pending":
        raise ExcuseError("هذا العذرُ ليس بانتظار النائب.")
    if not reason:
        raise ExcuseError("اكتب سببَ الرفض.")
    excuse.status = "rejected"
    excuse.rejection_reason = reason
    excuse.reviewed_by = by
    excuse.reviewed_at = timezone.now()
    excuse.save(update_fields=["status", "rejection_reason", "reviewed_by", "reviewed_at"])
    _audit(by, excuse.school, "update", excuse, {"decision": "rejected", "reason": reason}, ip=ip)


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

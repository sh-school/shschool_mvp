"""الحصّةُ المؤقّتة للمعلّم — يرصد غيابَ شعبةٍ مُسنَدةٍ إليه قبل اعتماد الجدول (W-20261005-006، قرارا المالك D-217م وD-218م).

**لِمَ**: رصدُ الغياب كان مغلقاً على جدول المنصّة المعتمَد — لا `Session` بلا `ScheduleSlot` — فلا يرصد المعلّمُ ريثما يُعتمد الجدول (بعد أسبوعين أو ثلاثة).
فالمعلّمُ ينشئ حصّةً مؤقّتةً (`Session.provisional`) لشعبةٍ **من إسناده** وفي **اليوم الدراسيّ الجاري**، ثمّ يرصد بالمسار القائم ويعتمد المشرفُ.

القواعدُ (كلُّها في الخدمة لا الواجهة وحدَها):

- **المفتاحُ**: `settings.PROVISIONAL_SESSIONS_ENABLED` — مطفأً لا إنشاءَ ولا مسار (404) فيعود السلوكُ السابق حرفاً (بند 13).
- **الإسنادُ**: المعلّمُ ينشئ لشُعب `SubjectClassAssignment` الفعّالة له فقط؛ شعبةٌ غيرُ مُسنَدةٍ ← `ProvisionalNotAllowedError` (404 لا 403: وجودُ الشعبة ليس شأنَه).
- **اليومُ**: اليومُ الدراسيّ الجاري وحدَه (`school_days`) — لا ماضيَ ولا مستقبل (D-215م «لا ماضيَ يسجَّل»)، وإلا 404.
- **رقمُ الحصّة** من 1 إلى 7، وزمنُها من `TimeSlotConfig` لجرس شعبتها (لا رقمَ يُعدّ زمناً في هذه المدرسة)؛ خارجَ المدى أو بلا زمنٍ مُعرَّف ← `ProvisionalRefusedError`.
- **التفرّد**: مؤقّتةٌ واحدةٌ لـ(شعبة، تاريخ، رقم حصّة) ولـ(معلّم، تاريخ، رقم حصّة) بقيدين مشروطَين؛ والإعادةُ بالمفتاح نفسِه تُرجع ما أُنشئ (متساوي الأثر).
  وتُرفض مؤقّتةٌ تصادم حصّةً **حقيقيّةً** لشعبتها أو لمعلّمها في الوقت نفسه.
- **السقفُ**: ما ينشئه المعلّمُ اليومَ لا يتجاوز خاناتِ جرسه، وما ينشئه في الساعة لا يتجاوز حدّاً صغيراً (سقفُ معدّل الطلبات).
- **المعاملة**: الإنشاءُ في `transaction.atomic` بقفل صفوف الإسناد (`select_for_update`)، وسباقٌ على القيد الفريد يُرجَع رفضاً لا خطأَ 500.
- **التدقيق**: سطرُ `AuditLog` بالمعرّفات لا الأسماء (PDPPL).

والمؤقّتةُ **تُغلق ولا تُحذف** (بند 14): `provisional_until` يُقصَّر إلى لحظة الإغلاق.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from django.conf import settings
from django.db import IntegrityError, transaction
from django.db.models import Q
from django.utils import timezone

from core.academic_calendar import academic_year_for_school
from core.models import AuditLog, ClassGroup
from operations.models import Session, SubjectClassAssignment, TimeSlotConfig
from operations.school_days import school_day

if TYPE_CHECKING:
    from core.models import CustomUser, School

#: ح1 … ح7 — رقمُ الحصّة المسموح به (بند 11).
PERIOD_NUMBERS = tuple(range(1, 8))
#: مدّةُ سريان المؤقّتة (بند 8): بعدها تنتهي إن لم يُعتمد الجدول.
VALIDITY = dt.timedelta(days=14)
#: سقفُ الإنشاء في الساعة لكلّ معلّم (سقفُ معدّل الطلبات، بند 2).
HOURLY_LIMIT = 30
#: وسمُ المؤقّتة في الشاشات والإحصاءات.
LABEL = "حصّة مؤقّتة"


class ProvisionalNotAllowedError(Exception):
    """ليس لك أن ترى هذا — يُترجم 404 (شعبةٌ غيرُ مُسنَدة، يومٌ غيرُ الجاري، مفتاحٌ مطفأ)."""


class ProvisionalRefusedError(Exception):
    """طلبٌ صحيحُ الصلاحيّة لكنّه مرفوضٌ ومعه السبب — يُعرض للمعلّم رسالةً."""


@dataclass(frozen=True)
class PeriodChoice:
    """خيارٌ في منتقي الحصّة: رقمُها وزمنُها، وهل لشعبته مؤقّتةٌ أنشأها المعلّمُ لها اليومَ."""

    number: int
    start: dt.time | None
    end: dt.time | None
    session: Session | None = None

    @property
    def available(self) -> bool:
        """للزمن المعرَّف وحدَه خيار؛ ورقمٌ بلا زمنٍ في جرس الشعبة يُعرض معطَّلاً."""
        return self.start is not None


def enabled() -> bool:
    """مفتاحُ التشغيل — مطفأً لا ميزةَ ولا مسار."""
    return bool(getattr(settings, "PROVISIONAL_SESSIONS_ENABLED", False))


def _assignments(user: CustomUser, school: School, klass: ClassGroup | None = None):
    """إسنادات المعلّم الفعّالةُ في عام المدرسة — لشعبةٍ بعينها أو كلِّها."""
    queryset = SubjectClassAssignment.objects.filter(
        school=school,
        teacher=user,
        is_active=True,
        deleted_at__isnull=True,
        academic_year=academic_year_for_school(school),
    )
    return queryset.filter(class_group=klass) if klass is not None else queryset


def assigned_classes(user: CustomUser, school: School) -> list[ClassGroup]:
    """شُعبُ إسناد المعلّم — لا شعبةَ غيرُها تُعرض ولا تُنشأ لها حصّة."""
    if not enabled():
        return []
    group_ids = _assignments(user, school).values_list("class_group_id", flat=True)
    return list(
        ClassGroup.objects.filter(pk__in=list(group_ids), school=school, is_active=True)
        .select_related("wing")
        .order_by("grade", "section")
    )


def assigned_class(user: CustomUser, school: School, class_id: Any) -> ClassGroup:
    """الشعبةُ إن كانت من إسناد المعلّم — وإلّا `ProvisionalNotAllowedError` (404)، فلا يُعرَف أنّها موجودة."""
    if not enabled():
        raise ProvisionalNotAllowedError("الميزةُ مطفأة")
    try:
        klass = ClassGroup.objects.select_related("time_band", "wing").get(
            pk=class_id, school=school, is_active=True
        )
    except (ClassGroup.DoesNotExist, ValueError, TypeError):
        raise ProvisionalNotAllowedError("لا شعبة") from None
    if not _assignments(user, school, klass).exists():
        raise ProvisionalNotAllowedError("ليست من إسنادك")
    return klass


def _open_day(school: School, day: dt.date | None) -> dt.date:
    """اليومُ الدراسيّ الجاري وحدَه — أيُّ تاريخٍ غيرُه أو يومٌ بلا دراسةٍ ← `ProvisionalNotAllowedError`."""
    today = timezone.localdate()
    if (day or today) != today or not school_day(school, today).is_open:
        raise ProvisionalNotAllowedError("لا حصّةَ مؤقّتةً إلا في اليوم الدراسيّ الجاري")
    return today


def _bell(school: School, klass: ClassGroup, day: dt.date) -> dict[int, tuple[dt.time, dt.time]]:
    """`{رقم: (بدء، نهاية)}` لحصص جرس الشعبة في هذا اليوم — من `TimeSlotConfig` لا من الرقم."""
    day_type = school_day(school, day).bell_day_type
    if not day_type or klass.time_band_id is None:
        return {}
    rows = TimeSlotConfig.objects.filter(
        school=school,
        band_id=klass.time_band_id,
        day_type=day_type,
        is_break=False,
        period_number__in=PERIOD_NUMBERS,
    )
    return {row.period_number: (row.start_time, row.end_time) for row in rows}


def period_choices(
    user: CustomUser, school: School, klass: ClassGroup, day: dt.date | None = None
) -> list[PeriodChoice]:
    """ح1…ح7 بأزمنتها لهذه الشعبة اليوم، ومع كلٍّ مؤقّتتُها إن وُجدت — لمنتقي الواجهة."""
    today = _open_day(school, day)
    bell = _bell(school, klass, today)
    mine = {
        s.period_number: s
        for s in Session.objects.filter(
            class_group=klass, date=today, provisional=True, teacher=user
        )
    }
    return [
        PeriodChoice(n, *(bell.get(n) or (None, None)), session=mine.get(n)) for n in PERIOD_NUMBERS
    ]


def create(
    user: CustomUser,
    school: School,
    class_id: Any,
    period_number: Any,
    *,
    subject_id: Any = None,
    day: dt.date | None = None,
    request: Any = None,
) -> tuple[Session, bool]:
    """ينشئ حصّةً مؤقّتةً للمعلّم في شعبةٍ من إسناده وفي اليوم الجاري — `(الحصّة، أُنشئت الآن؟)`.

    متساوي الأثر: إعادةُ الطلب نفسِه تُرجع الحصّةَ القائمةَ (`False`) ولا تُكرّر.
    """
    klass = assigned_class(user, school, class_id)
    today = _open_day(school, day)
    try:
        number = int(period_number)
    except (TypeError, ValueError):
        raise ProvisionalRefusedError("رقمُ الحصّة غيرُ صالح") from None
    if number not in PERIOD_NUMBERS:
        raise ProvisionalRefusedError("رقمُ الحصّة من 1 إلى 7")
    times = _bell(school, klass, today).get(number)
    if times is None:
        raise ProvisionalRefusedError("لا زمنَ مُعرَّفاً لهذه الحصّة في جرس هذه الشعبة")
    start, end = times

    try:
        with transaction.atomic():
            # قفلُ صفوف الإسناد: طلبان متزامنان لمعلّمٍ واحدٍ يتسلسلان فلا يتجاوزان السقف معاً.
            assignments = list(_assignments(user, school, klass).select_for_update())
            if not assignments:
                raise ProvisionalNotAllowedError("ليست من إسنادك")
            subject = _subject_of(assignments, subject_id)

            existing = Session.objects.filter(
                class_group=klass, date=today, provisional=True, period_number=number, teacher=user
            ).first()
            if existing is not None:
                return existing, False

            _guard(user, klass, today, start, number)
            session = Session.objects.create(
                school=school,
                class_group=klass,
                teacher=user,
                subject=subject,
                date=today,
                start_time=start,
                end_time=end,
                period_number=number,
                status="scheduled",
                provisional=True,
                provisional_until=timezone.now() + VALIDITY,
                notes=LABEL,
            )
            AuditLog.log(
                user=user,
                action="create",
                model_name="other",
                object_id=session.pk,
                object_repr=f"{LABEL} — إنشاءٌ من المعلّم",
                changes={"class_group": str(klass.pk), "date": today.isoformat(), "period": number},
                school=school,
                request=request,
            )
    except IntegrityError:
        # سباقٌ على القيد الفريد المشروط: خسر هذا الطلبُ فيُرفض بمعنى لا بـ500.
        raise ProvisionalRefusedError("سبقتْه حصّةٌ مؤقّتةٌ لهذه الخانة") from None
    return session, True


def _subject_of(assignments: list[SubjectClassAssignment], subject_id: Any):
    """مادّةُ الحصّة: الوحيدةُ إن كان إسنادٌ واحد، وإلا المطلوبةُ من إسناداته."""
    by_subject = {a.subject_id: a.subject for a in assignments}
    if subject_id:
        found = next((s for pk, s in by_subject.items() if str(pk) == str(subject_id)), None)
        if found is None:
            raise ProvisionalNotAllowedError("مادّةٌ ليست من إسنادك")
        return found
    if len(by_subject) == 1:
        return next(iter(by_subject.values()))
    raise ProvisionalRefusedError("اختر المادّة: للمعلّم أكثرُ من مادّةٍ في هذه الشعبة")


def _guard(
    user: CustomUser, klass: ClassGroup, today: dt.date, start: dt.time, number: int
) -> None:
    """حراسُ الإنشاء: لا تصادمَ مع حقيقيّةٍ، ولا تجاوزَ للسقف اليوميّ ولا لمعدّل الساعة."""
    live = Session.objects.filter(date=today, start_time=start).exclude(status="cancelled")
    if live.filter(class_group=klass).exists():
        raise ProvisionalRefusedError("لهذه الشعبة حصّةٌ في هذا الوقت")
    if live.filter(teacher=user).exists():
        raise ProvisionalRefusedError("لك حصّةٌ أخرى في هذا الوقت")
    if Session.objects.filter(teacher=user, date=today, provisional=True).count() >= len(
        PERIOD_NUMBERS
    ):
        raise ProvisionalRefusedError("بلغتَ سقفَ الحصص المؤقّتة اليوم")
    recent = Session.objects.filter(
        teacher=user, provisional=True, created_at__gte=timezone.now() - dt.timedelta(hours=1)
    ).count()
    if recent >= HOURLY_LIMIT:
        raise ProvisionalRefusedError("طلباتٌ كثيرةٌ في الساعة الأخيرة — حاول لاحقاً")


def close(session: Session, *, reason: str, by: Any = None) -> bool:
    """يُغلق مؤقّتةً **ولا يحذفها**: `provisional_until` إلى الآن ما دامت سارية، وسطرُ تدقيقٍ بالسبب (بلا PII). `True` إن أُغلقت الآن."""
    # الحالةُ تُقرأ من القاعدة لا من الكائن: إغلاقٌ سابقٌ (أو من طلبٍ آخر) لا يُكرَّر ولا يُدقَّق مرّتين.
    now = timezone.now()
    closed = Session.objects.filter(pk=session.pk, provisional=True).filter(
        Q(provisional_until__isnull=True) | Q(provisional_until__gt=now)
    )
    if closed.update(provisional_until=now) == 0:
        return False
    AuditLog.log(
        user=by,
        action="update",
        model_name="other",
        object_id=session.pk,
        object_repr=f"{LABEL} — إغلاق",
        changes={"reason": reason, "date": session.date.isoformat()},
        school=session.school,
    )
    return True

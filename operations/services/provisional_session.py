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
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.models import Exists, OuterRef, Q
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
#: سقفُ محاولات الإنشاء في الساعة لكلّ معلّم (تُعدّ المرفوضةُ أيضاً).
ATTEMPTS_PER_HOUR = 60
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

    @property
    def state(self) -> str:
        """حالةُ الحصّة الآن للمنتقي: `current` جاريةٌ، `past` انقضت، `future` لم تبدأ (بلا زمنٍ: `future`)."""
        if self.start is None or self.end is None:
            return "future"
        now = timezone.localtime().time()
        if now < self.start:
            return "future"
        return "current" if now < self.end else "past"


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
    close_shadowed(school, today)
    bell = _bell(school, klass, today)
    mine = {
        s.period_number: s
        for s in Session.objects.filter(
            class_group=klass, date=today, provisional=True, teacher=user
        )
    }
    own_real = {
        s.start_time: s
        for s in Session.objects.filter(
            class_group=klass, date=today, teacher=user, provisional=False
        ).exclude(status="cancelled")
    }
    return [
        PeriodChoice(
            n,
            *(bell.get(n) or (None, None)),
            session=mine.get(n) or own_real.get((bell.get(n) or (None,))[0]),
        )
        for n in PERIOD_NUMBERS
    ]


def _default_period(bell: dict) -> int:
    """رقمُ الحصّة الافتراضيّ من جرس الشعبة الآن — جاريةٌ ثمّ آخرُ ماضيةٍ ثمّ أوّلُ قادمة."""
    choices = [PeriodChoice(n, *(bell.get(n) or (None, None))) for n in PERIOD_NUMBERS]
    defined = [c for c in choices if c.available]
    if not defined:
        raise ProvisionalRefusedError("لا زمنَ مُعرَّفاً لأيّ حصّةٍ في جرس هذه الشعبة")
    for choice in defined:
        if choice.state == "current":
            return choice.number
    past = [c for c in defined if c.state == "past"]
    return (past[-1] if past else defined[0]).number


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
    _throttle(user)
    close_shadowed(school, today)
    if period_number in (None, ""):
        # «ارصد» بلا اختيارٍ: الحصّةُ الجاريةُ الآن، وإلا آخرُ ما انقضى، وإلا أوّلُ القادمة (النافذةُ مفتوحةٌ من بدء جرس الشعبة).
        number = _default_period(_bell(school, klass, today))
    else:
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
            # كلُّ إسنادات المعلّم لا إسنادُ هذه الشعبة وحدَها: طلبان على شعبتين مختلفتين يتسلسلان فلا يتجاوزان السقفَ معاً (مراجعة 0104، 4).
            held = list(_assignments(user, school).select_for_update())
            assignments = [a for a in held if a.class_group_id == klass.pk]
            if not assignments:
                raise ProvisionalNotAllowedError("ليست من إسنادك")
            subject = _subject_of(assignments, subject_id)

            existing = Session.objects.filter(
                class_group=klass, date=today, provisional=True, period_number=number, teacher=user
            ).first()
            if existing is not None:
                return existing, False
            # حصّةٌ **حقيقيّةٌ للمعلّم نفسِه** في هذه الشعبة والوقت (جدولٌ أو إسنادٌ للمعاينة): تُفتح لا تُرفض ولا تُنشأ فوقها مؤقّتة.
            own_real = (
                Session.objects.filter(
                    class_group=klass,
                    date=today,
                    start_time=start,
                    teacher=user,
                    provisional=False,
                )
                .exclude(status="cancelled")
                .first()
            )
            if own_real is not None:
                return own_real, False

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


def _throttle(user: CustomUser) -> None:
    """سقفُ **معدّل الطلبات** لا الصفوفِ المُنشأة فقط (بند 2، مراجعة 0104، 3): كلُّ محاولةٍ تُعدّ ولو رُفضت — فلا تعدادَ بالتجريب."""
    key = f"provisional:attempts:{user.pk}:{timezone.now():%Y%m%d%H}"
    cache.add(key, 0, timeout=3600)
    try:
        attempts = cache.incr(key)
    except ValueError:  # انقضى المفتاحُ بين add وincr
        cache.set(key, 1, timeout=3600)
        attempts = 1
    if attempts > ATTEMPTS_PER_HOUR:
        raise ProvisionalRefusedError("طلباتٌ كثيرةٌ في الساعة الأخيرة — حاول لاحقاً")


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
    """حراسُ الإنشاء: السقفُ اليوميّ ومعدّلُ الساعة (ولا رفضَ لتصادمٍ مع حقيقيّةٍ لمعلّمٍ آخر — D-229م)."""
    # لا يُرفض الإنشاءُ لوجود حصّةٍ حقيقيّةٍ لمعلّمٍ آخر في الشعبة والوقت (قرارُ المالك D-229م): جدولُ المنصّة غيرُ المعتمد قد يخالف الجدولَ الخارجيَّ المعمولَ به
    # تماماً، فتلك الحصّةُ المولَّدةُ ليست الحقيقةَ — والمؤقّتةُ هي ما يرصده المعلّم فعلاً. والازدواجُ لا يُعدّ مرّتين لأنّ التقارير تحسب الطالبَ بخانة الساعة
    # (حاضرٌ في إحدى حصّتَي الخانة حاضر) لا بعدد الجلسات، وصفوفُ الرصد لا تُكتب إلا حيث رُصد.
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


def close_shadowed(school: School, day: dt.date) -> int:
    """يُغلق مؤقّتاتِ يومٍ **زاحمتها حصّةٌ حقيقيّة** في خانتها (بند 10، D-219م) — بلا اعتماد على مولّدٍ بعينه.

    الحقيقيّةُ تعني صفّاً غيرَ مؤقّتٍ غيرَ ملغًى بالساعة نفسِها لشعبة المؤقّتة **ولمعلّمها معاً** (نسخةٌ مكرَّرةٌ من الحصّة نفسِها)؛ أمّا حقيقيّةٌ لمعلّمٍ آخر فلا تُغلق
    مؤقّتةً (D-229م: جدولُ المنصّة غيرُ المعتمد قد يخالف الواقعَ فلا يُقدَّم على رصد المعلّم) — وتُغلق المؤقّتاتُ كلُّها عند اعتماد الجدول (بند 14). المصدرُ لا يهمّ:
    المولّدُ الحاليّ (`bulk_create` بلا إشاراتٍ) أو V2 أو تبديلٌ أو إنشاءٌ يدويّ — فالقاعدةُ على مستوى `Session` نفسِها. ويُستدعى حيث تُقرأ المؤقّتات
    (الإنشاءُ ومنتقي الشعبة) وبإشارةٍ عند حفظ حقيقيّةٍ جديدة؛ والمؤقّتةُ تُغلق ولا تُحذف، وكلُّ إغلاقٍ بسطر تدقيق. يرجع عددَ ما أُغلق.
    """
    if not enabled():
        return 0
    real = (
        Session.objects.filter(
            provisional=False,
            date=OuterRef("date"),
            start_time=OuterRef("start_time"),
        )
        .exclude(status="cancelled")
        # **الحقيقيّةُ المطابقةُ فقط**: الشعبةُ والمعلّمُ كلاهما — فالمؤقّتةُ حينئذٍ نسخةٌ مكرَّرةٌ من الحصّة نفسِها. حصّةٌ حقيقيّةٌ لمعلّمٍ آخر لا تُغلقها (D-229م).
        .filter(class_group_id=OuterRef("class_group_id"), teacher_id=OuterRef("teacher_id"))
    )
    now = timezone.now()
    shadowed = (
        Session.objects.filter(school=school, date=day, provisional=True)
        .filter(Q(provisional_until__isnull=True) | Q(provisional_until__gt=now))
        .filter(Exists(real))
    )
    return sum(close(session, reason="real_session_exists") for session in list(shadowed))


def class_page_context(
    user: CustomUser, school: School, klass: ClassGroup, session_id: Any = None
) -> dict[str, Any]:
    """سياقُ صفحة الشعبة للرصد المؤقّت: المنتقي ح1–ح7 وقائمةُ الطلبة، ومع الحصّة المختارة `?session=` **شبكةُ كشف الحصّة نفسُها** (D-229م).

    الحصّةُ المختارةُ تُقبل إن كانت **حصّةَ هذا المعلّم اليومَ في هذه الشعبة** وإلا لا شبكة (لا يُكشف وجودُ غيرها). في الخدمة لا العرض: سقّاطةُ الطبقات.
    `ProvisionalNotAllowedError` لغير اليوم الدراسيّ الجاري.
    """
    from .attendance_teacher import TeacherAttendanceService

    context: dict[str, Any] = {
        "klass": klass,
        "choices": period_choices(user, school, klass),
        "provisional_pick": True,
    }
    chosen = _chosen_session(user, school, klass, session_id)
    if chosen is not None:
        context.update(
            {
                **TeacherAttendanceService.page_context(user, chosen),
                **TeacherAttendanceService.sheet(user, chosen),
            }
        )
    return context


def _chosen_session(
    user: CustomUser, school: School, klass: ClassGroup, raw: Any
) -> Session | None:
    if not raw:
        return None
    try:
        return (
            Session.objects.select_related("class_group__wing", "subject")
            .exclude(status="cancelled")
            .get(
                pk=raw,
                school=school,
                class_group=klass,
                teacher=user,
                date=timezone.localdate(),
            )
        )
    except (Session.DoesNotExist, ValueError, ValidationError):
        return None

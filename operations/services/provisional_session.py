"""الحصّةُ المؤقّتة — أساسُ أعمدة جدول الشعبة (W-20261005-006، قرارا المالك D-217م وD-218م).

كلُّ عمودٍ في جدول الشعبة حصّةٌ مؤقّتةٌ (`Session.provisional`) بمعلّمٍ مُسنَدٍ حتميّ؛ وهي **تُغلق ولا تُحذف** (بند 14):
`provisional_until` يُقصَّر إلى لحظة الإغلاق. وهنا ثوابتُها وأزمنةُ الجرس وإغلاقُ ما زاحمته حصّةٌ حقيقيّة.
(حُذف منتقي الحصّة والإنشاءُ منه: الجدولُ هو الواجهةُ الوحيدة — W-20261009-003.)
"""

from __future__ import annotations

import datetime as dt
from typing import TYPE_CHECKING, Any

from django.conf import settings
from django.db.models import Exists, OuterRef, Q
from django.utils import timezone

from core.models import AuditLog, ClassGroup
from operations.models import Session, TimeSlotConfig
from operations.school_days import school_day

if TYPE_CHECKING:
    from core.models import School

#: ح1 … ح7 — رقمُ الحصّة المسموح به (بند 11).
PERIOD_NUMBERS = tuple(range(1, 8))
#: مدّةُ سريان المؤقّتة (بند 8): بعدها تنتهي إن لم يُعتمد الجدول.
VALIDITY = dt.timedelta(days=14)
#: وسمُ المؤقّتة في الشاشات والإحصاءات.
LABEL = "حصّة مؤقّتة"


def enabled() -> bool:
    """هل «بابُ الجدول» مشغَّلٌ؟ — يُطفئ للمعلّم والمنسّق جدولَ المنصّة غيرَ المعتمَد (وسمُ القوالب `provisional_door`، D-228م).

    لا يخصّ جدولَ الشعبة العموديَّ: هو يعمل دائماً بلا مفتاح (W-20261009-003). المفتاحُ الباقي `PROVISIONAL_GRID_ENABLED` في البيئة
    يقرّر وحدَه إخفاءَ روابط جدول الحصص للمعلّم؛ وبقاؤه أو حذفُه قرارُ المالك.
    """
    return bool(getattr(settings, "PROVISIONAL_GRID_ENABLED", False))


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


def bell_periods(
    school: School, klass: ClassGroup, day: dt.date
) -> dict[int, tuple[dt.time, dt.time]]:
    """`{رقم: (بدء، نهاية)}` لحصص جرس الشعبة — واجهةٌ عامّةٌ لجدول الشعبة (لا رقمَ يُعدّ زمناً)."""
    return _bell(school, klass, day)


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

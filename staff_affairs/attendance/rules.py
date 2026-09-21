"""القواعدُ الصرفة: الدوامُ والحدودُ وتصنيفُ الحضور ونوافذُ الأذون — بلا قاعدةِ بيانات.

من تفكيك ``staff_affairs/attendance.py`` (الحزمةُ تُصدّر الأسماءَ نفسَها في ``__init__``).
"""

from __future__ import annotations

import calendar
from collections.abc import Iterable
from datetime import date, datetime, time, timedelta

from staff_affairs.models import (
    ABSENCE_TYPES,
)

from .context import (
    PolicyError,
    _minute,
    minutes_between,
)

#: م-1 (السياسة 1.1) — بدايةُ الدوام، وما بعدها تأخّر (م-3).
WORK_START = time(7, 0)
#: م-1 (السياسة 1.1) — «وينتهي في تمام الثانية ظهراً».
WORK_END = time(14, 0)
#: م-4 (السياسة 2.4) — ما بعدها غيابٌ بلا تغطيةٍ سارية ولا عذرٍ مقبول.
ABSENT_AFTER = time(9, 0)
#: م-15 — عشرُ ساعاتٍ في الشهر: قانونُ الموارد البشرية 15/2016 (المعدَّل 25/2025)،
#: المادّة 79، البند 3: «بحدّ أقصى عشر ساعات في الشهر». وقرارُ المالك 2026-09-19 اعتمادُ
#: حدّ القانون بدل سبع ساعاتٍ في السياسة الداخلية 4.2؛ وما فوقه بموافقةٍ كتابيّة.
MONTHLY_PERMIT_CAP = 10 * 60
#: م-13 — ثلاثُ ساعاتٍ للمرّة (المادّة 79، البند 3 نفسُه)، و180 مقبولة؛ وما فوقها بموافقةٍ كتابيّة.
PERMIT_MAX_MINUTES = 3 * 60
#: م-35 (السياسة 5.3) — «تغطية أيام غيابه قبل يوم (15) من الشهر»: المهلةُ تنتهي بنهاية
#: اليوم الرابع عشر من الشهر التالي، وما بعدها يُسجَّل ويُوسم لا يُمنع.
COVERAGE_DEADLINE_DAY = 14

#: أيّامُ الدوام الأسبوعيّ: الأحد–الخميس، كما في الجدول المدرسيّ نفسِه (خمسةُ أيّامٍ
#: بأسمائها في مولّد الجدول) — ومنها تُعدّ أيّامُ الاستثناء في التقرير (م-33).
SCHOOL_WEEKDAYS = frozenset({6, 0, 1, 2, 3})  # ``date.weekday()``: الأحد 6 … الخميس 3

STATUSES = ("present", "late", "absent", "permitted")
STATUS_LABELS = {"present": "حاضر", "late": "متأخّر", "absent": "غائب", "permitted": "مستأذن"}
#: حالاتُ من حضر — لا تُرصد إلّا بوقت حضوره، فبه تُحسب دقائقُ التأخّر (م-3 وم-6).
ARRIVAL_STATUSES = ("present", "late", "permitted")
ABSENCE_TYPE_KEYS = tuple(key for key, _label in ABSENCE_TYPES)
#: م-18ب — نوعان يُقدَّمان قبل وقت بدئهما، وما لم يُعتمد قبله يصير «منتهياً».
LEAVING_PERMIT_TYPES = ("during_day", "early_departure")


def classify_arrival(
    check_in: time,
    covered_until: time | None = None,
    excused: bool = False,
    windows: Iterable[tuple[time, time]] = (),
) -> tuple[str, int]:
    """(الحالة، دقائقُ التأخّر) لوقت حضورٍ — م-3 وم-4 وم-5 وم-6.

    ``windows`` نوافذُ اليوم المعتمدة كلُّها (م-5 لا تفرّق بين الأنواع): أذوناتُ نموذج 02
    الثلاثة واستثناءاتُ نموذج 03 (م-32)؛ و``covered_until`` اختصارٌ لنافذةٍ من 7:00.

    * من حضر داخل نافذةٍ بدأت قبل حضوره «مستأذن» (م-5) — ولو بعد التاسعة، فهي «إذنٌ
      يغطّي لحظةَ حضوره» (م-4).
    * ومن جاوز النوافذَ حتّى التاسعة «متأخّر»، ودقائقُه من اللحظة الأبعد بين 07:00 ونهاية
      آخر تغطيةٍ انتهت قبل حضوره (م-6)؛ ومن جاوزها وجاوز التاسعة «غائب» إلّا أن يُقبل
      عذرُه (``excused``، م-7).
    * والمستأذنُ بنافذةٍ بدأت بعد 07:00 تُعدّ عليه الدقائقُ غيرُ المأذونة قبل بدئها — من
      تلك اللحظة نفسِها إلى بدء النافذة — فلا تُخصم المأذونةُ مرّتين (حجّة م-6) ولا تُسقط
      نافذةٌ متأخّرةٌ ما قبلها. وهذا الامتدادُ قراءةٌ لحجّة م-6 (المصدر صامت، س-5).
    """
    check_in = _minute(check_in)
    if check_in <= WORK_START:
        return "present", 0
    spans = [(_minute(start), _minute(end)) for start, end in windows]
    if covered_until is not None:
        spans.append((WORK_START, _minute(covered_until)))
    counted_from = WORK_START
    for start, end in sorted(spans):
        if start >= check_in:
            break
        if check_in <= end:
            return "permitted", minutes_between(counted_from, start)
        counted_from = max(counted_from, end)
    if check_in <= ABSENT_AFTER or excused:
        return "late", minutes_between(counted_from, check_in)
    return "absent", 0


def early_leave_minutes(check_out: time, windows: Iterable[tuple[time, time]] = ()) -> int:
    """م-8 وم-5: دقائقُ الخروج المبكر — ما بين الانصراف و14:00 ممّا لا تغطّيه نافذةٌ معتمدة.

    ``windows`` نوافذُ اليوم المعتمدة (خروجٌ مبكر أو استئذانٌ من نموذج 02، أو استثناءُ
    خروجٍ من نموذج 03). والتغطيةُ الممتدّة إلى 14:00 — نظيرةُ تغطية الصباح الممتدّة من
    07:00 في م-6 — تجعل الحسابَ «من الانصراف إلى أقرب اللحظتين: 14:00 أو بدءِ التغطية»
    بنصّ م-8. أمّا نافذةٌ في وسط الدوام فتغطّي دقائقَها وحدَها (م-5: «ولا يلحق اليوم
    كلّه»)، فلا يُسقط استئذانُ دقيقةٍ بعد الانصراف بقيّةَ اليوم، ولا تُعدّ دقيقةٌ مأذونةٌ
    مرّتين (حجّة م-6). والحسابُ اختيارٌ هندسيٌّ مؤقّت (المصدر صامت).
    """
    check_out = _minute(check_out)
    if check_out >= WORK_END:
        return 0
    covered: list[tuple[time, time]] = []
    for raw_start, raw_end in sorted((_minute(s), _minute(e)) for s, e in windows):
        start, end = max(raw_start, check_out), min(raw_end, WORK_END)
        if end <= start:
            continue
        if covered and start <= covered[-1][1]:
            covered[-1] = (covered[-1][0], max(covered[-1][1], end))
        else:
            covered.append((start, end))
    return minutes_between(check_out, WORK_END) - sum(
        minutes_between(start, end) for start, end in covered
    )


def month_bounds(day: date) -> tuple[date, date]:
    last = calendar.monthrange(day.year, day.month)[1]
    return day.replace(day=1), day.replace(day=last)


def coverage_deadline(day: date) -> date:
    """م-35: آخرُ يومٍ تُقبل فيه تغطيةُ غياب ``day`` بلا وسم — الرابعَ عشرَ من الشهر التالي."""
    first, last = month_bounds(day)
    return (last + timedelta(days=1)).replace(day=COVERAGE_DEADLINE_DAY)


def _check_submission_window(day: date, now: datetime) -> None:
    """م-18أ: تاريخُ إذن التأخير الصباحيّ — الشهرُ الجاري، أو السابقُ ما لم يتجاوز اليومُ 14.

    فالبند 5.1 يُشعر بتقرير الشهر السابق «بداية كل شهر»، و5.3 يمهل التغطية «قبل يوم
    (15) من الشهر» — فما قبل ذلك كلَّه باب التسوية، وما بعده أُغلق تقريرُه.
    """
    first_of_month = now.date().replace(day=1)
    if day >= first_of_month:
        return
    if now.day <= COVERAGE_DEADLINE_DAY and day >= (first_of_month - timedelta(days=1)).replace(
        day=1
    ):
        return
    raise PolicyError(
        f"شهرُ {day:%Y-%m} أُغلق: التقريرُ يُشعَر به بداية الشهر التالي (البند 5.1) "
        f"والتغطيةُ قبل يوم 15 منه (البند 5.3) — فلا إذنَ يُقدَّم له الآن."
    )


def _check_window(permit_type: str, start: time, end: time) -> None:
    """م-1 وم-12 وم-13: نافذةُ الإذن داخلَ الدوام وعلى قدر نوعه.

    التأخيرُ الصباحيّ يبدأ من 7:00 لأنّ التأخّرَ يُعدّ من بعدها (م-3)، والخروجُ المبكر
    ينتهي بنهاية الدوام 14:00، والاستئذانُ أثناء الدوام بينهما.
    """
    if start < WORK_START or end > WORK_END:
        raise PolicyError("نافذةُ الإذن خارجَ الدوام الرسميّ 7:00–14:00 (البند 1.1).")
    if permit_type == "late_arrival" and start != WORK_START:
        raise PolicyError(
            "التأخيرُ الصباحيّ يبدأ من 7:00 — فالتأخّرُ يُعدّ من بعدها (البند 2.1)؛ "
            "وما يبدأ بعدها «استئذانٌ أثناء الدوام»."
        )
    if permit_type == "early_departure" and end != WORK_END:
        raise PolicyError(
            "الخروجُ المبكر ينتهي بنهاية الدوام 14:00 (البند 1.1)؛ "
            "وما ينتهي قبلها «استئذانٌ أثناء الدوام»."
        )
    if permit_type == "during_day" and (start == WORK_START or end == WORK_END):
        raise PolicyError(
            "استئذانٌ يبدأ 7:00 تأخيرٌ صباحيّ، وما ينتهي 14:00 خروجٌ مبكر (البندان 1.1 و2.1)."
        )


def _check_timing(permit_type: str, day: date, start: time, now: datetime) -> None:
    """م-18أ وم-18ب وم-11: متى يُقدَّم الطلب.

    حاشيةُ ن02 بنصّها (أصل PDF ص1، وdocx النموذج): «في حال تقديم الطلب فإنه يتعين على
    الموظف عدم الخروج إلا بعد اعتماده وإخطاره من قبل السكرتارية بالموافقة على طلب
    الاجازة.» و«لا يعتبر الطلب معتمداً الا باعتماد مدير المدرسة وتوقيعه عليه.» —
    فالخروجُ والاستئذانُ يُطلبان قبل وقت بدئهما.

    والتأخيرُ الصباحيّ يُطلب قبل وقوعه أو بعده (م-18أ): يُبلَّغ المسؤولُ لحظتَها بالبريد
    (البند 2.2) ثمّ يُرفع الإذن (4.5) — وتُقبل المنصّةُ طلبَ الغد في أيّ ساعة (م-11).
    """
    if permit_type == "late_arrival":
        _check_submission_window(day, now)
        return
    if (day, _minute(start)) <= (now.date(), _minute(now.time())):
        raise PolicyError(
            "الخروجُ والاستئذانُ يُطلبان قبل وقت بدئهما — «يتعين على الموظف عدم الخروج "
            "إلا بعد اعتماده وإخطاره من قبل السكرتارية بالموافقة» (حاشية نموذج 02)."
        )

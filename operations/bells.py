"""جرسُ الطابق والجناح — وما يرنّ الآن يُقال بالساعة لا برقم الحصّة.

المدرسةُ طابقان وأجراسُها ثلاثة، ومن الأحد إلى الأربعاء اثنان فقط يفترقان:
الأرضيُّ فسحتُه بعد الثالثة، والأوّلُ بعد الرابعة. ويومَ الخميس ثلاثةٌ: تاسع
3·4 يفترقون عن الثانويّ.

فرقمُ الحصّة **ليس** وقتاً في هذه المدرسة. «الحصّةُ الرابعة» في الأرضيّ تبدأ
10:00 وفي الأوّل 9:35 — ومن بنى شاشةً على الرقم أخبر مشرفَ جناحٍ أنّ حصّةً
تجري وقد انتهت، أو أنّها انتهت ولم تبدأ. وجناح 3 أسوأُ من ذلك: **ممرٌّ بجرسين**
(تاسع 3·4 على `ninth` والعاشر على `secondary`) فلا جوابَ واحدٌ لسؤال «ما
الحصّةُ الآن؟» فيه أصلاً — جوابانِ، ولذلك تُرجع `wing_position` قائمةً لا
قيمةً واحدة.

## لِمَ وحدةٌ مستقلّة

`TimeSlotConfig` بيانٌ خامّ: صفٌّ لكلّ حصّةٍ لكلّ جرسٍ لكلّ نوعِ يوم. وقراءتُه
حيث يُحتاج تُنتج استعلاماً في حلقة (خمسةُ أجنحة × جرسٍ أو جرسين)، وتُعيد
تسميةَ الاستراحات في كلّ موضع. فالتجميعُ هنا مرّةً واحدة: `bells_for` استعلامٌ
واحدٌ يُخرج أجراسَ المدرسة كلَّها، وما بعده قسمةٌ في الذاكرة.

## والطابقُ محفوظٌ لا مخمَّن

`TimeBand.floor` حقلٌ في القاعدة، فلا يُستدلّ على الطابق من الرمز: `ninth`
و`secondary` طابقٌ واحدٌ ورمزاهما مختلفان، واستدلالٌ بالأسماء يكذب في أوّل
جرسٍ يُضاف.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass

from operations.models import TimeSlotConfig

#: نوعا اليوم المبذوران. و`ramadan` خيارٌ في النموذج لم يُبذَر بعد — فمن
#: طلبه يُرجَع بجرسٍ فارغٍ لا بجرسٍ خطأ.
REGULAR = "regular"
THURSDAY = "thursday"

#: يومُ بايثون (الاثنين 0 … الأحد 6) → نوعُ اليوم المدرسيّ. والجمعةُ والسبتُ
#: ليسا فيها: لا دراسةَ فيهما، ولا جرسَ يُعرض.
_DAY_TYPE = {6: REGULAR, 0: REGULAR, 1: REGULAR, 2: REGULAR, 3: THURSDAY}


def day_type_for(day: dt.date) -> str:
    """نوعُ اليوم المدرسيّ، و`""` ليومٍ لا دراسةَ فيه."""
    return _DAY_TYPE.get(day.weekday(), "")


@dataclass(frozen=True)
class Slot:
    """خانةٌ في اليوم: حصّةٌ أو فسحةٌ أو صلاة."""

    number: int
    label: str
    start: dt.time
    end: dt.time
    is_break: bool

    def holds(self, moment: dt.time) -> bool:
        """نهايةُ الخانة ليست فيها: 9:35 آخرُ الثالثة أوّلُ الفسحة."""
        return self.start <= moment < self.end


@dataclass(frozen=True)
class Bell:
    """جرسٌ واحدٌ في يومٍ واحد — خاناتُه مرتّبةٌ بالساعة لا بالرقم.

    والترتيبُ بالساعة شرطٌ لا ذوق: الصلاةُ في الأرضيّ رقمُها 101 ووقتُها
    12:20، أي **قبل** الحصّة السابعة. فترتيبٌ بالرقم يضعها آخرَ اليوم.
    """

    band_code: str
    band_name: str
    floor: str
    day_type: str
    slots: tuple[Slot, ...]

    @property
    def periods(self) -> tuple[Slot, ...]:
        return tuple(slot for slot in self.slots if not slot.is_break)

    @property
    def starts(self) -> dt.time | None:
        return self.slots[0].start if self.slots else None

    @property
    def ends(self) -> dt.time | None:
        return self.slots[-1].end if self.slots else None

    def running(self, moment: dt.time) -> Slot | None:
        """الخانةُ الجارية — و`None` في فرجةٍ بين خانتين أو خارجَ اليوم."""
        return next((slot for slot in self.slots if slot.holds(moment)), None)

    def upcoming(self, moment: dt.time) -> Slot | None:
        """أوّلُ خانةٍ لم تبدأ بعد."""
        return next((slot for slot in self.slots if slot.start > moment), None)


@dataclass(frozen=True)
class Position:
    """موضعُ جرسٍ من لحظةٍ: ما يجري فيه وما يليه."""

    bell: Bell
    running: Slot | None
    upcoming: Slot | None

    @property
    def says(self) -> str:
        """جملةٌ تُقرأ في شاشة — الساعةُ فيها لأنّ الرقمَ وحدَه لا يُميّز."""
        if self.running:
            end = f"{self.running.end:%H:%M}"
            return f"{self.running.label} · حتّى {end}"
        if self.upcoming:
            start = f"{self.upcoming.start:%H:%M}"
            return f"قبل {self.upcoming.label} · تبدأ {start}"
        return "انتهى الدوام"


def _label(row: TimeSlotConfig) -> str:
    return row.break_label or f"الحصّة {row.period_number}"


def bells_for(school, day_type: str) -> dict[str, Bell]:
    """أجراسُ المدرسة في هذا اليوم: رمزُ الجرس → `Bell` — باستعلامٍ واحد.

    ومن لا جرسَ له (`band=None`) يُطرح: خانةُ «جرسِ المدرسة الافتراضيّ» بقيّةٌ
    من قبل النطاقات، وخلطُها بجرسٍ مسمّىً يُنتج يوماً بحصّتين رابعتين.
    """
    rows = (
        TimeSlotConfig.objects.filter(school=school, day_type=day_type, band__isnull=False)
        .select_related("band")
        .order_by("band__order", "start_time")
    )
    grouped: dict[str, list[Slot]] = {}
    meta: dict[str, TimeSlotConfig] = {}
    for row in rows:
        grouped.setdefault(row.band.code, []).append(
            Slot(
                number=row.period_number,
                label=_label(row),
                start=row.start_time,
                end=row.end_time,
                is_break=row.is_break,
            )
        )
        meta.setdefault(row.band.code, row)

    return {
        code: Bell(
            band_code=code,
            band_name=meta[code].band.name,
            floor=meta[code].band.floor,
            day_type=day_type,
            slots=tuple(slots),
        )
        for code, slots in grouped.items()
    }


def wing_bells(wing, day_type: str, table: dict[str, Bell] | None = None) -> list[Bell]:
    """أجراسُ الجناح — واحدٌ في الغالب، واثنان في جناحٍ يعبر جرسين.

    و`table` يُمرَّر حين تُعرض الأجنحةُ الخمسةُ معاً، فيُقرأ الجرسُ مرّةً لا
    خمساً.
    """
    if not day_type:
        return []
    known = table if table is not None else bells_for(wing.school, day_type)
    return [known[band.code] for band in wing.time_bands if band.code in known]


def floor_bells(
    school, floor: str, day_type: str, table: dict[str, Bell] | None = None
) -> list[Bell]:
    """أجراسُ طابقٍ كامل — والأوّلُ منها جرسان."""
    if not day_type:
        return []
    known = table if table is not None else bells_for(school, day_type)
    return [bell for bell in known.values() if bell.floor == floor]


def wing_position(wing, when: dt.datetime, table: dict[str, Bell] | None = None) -> list[Position]:
    """موضعُ الجناح من هذه اللحظة — موضعٌ لكلّ جرسٍ فيه.

    وقائمةٌ لا قيمةٌ واحدة: جناح 3 بجرسين، فـ«الحصّةُ الآن» فيه سؤالٌ جوابُه
    اثنان — وقيمةٌ واحدةٌ تعني اختيارَ أحدِهما صامتاً وتكذيبَ نصفِ الممرّ.
    """
    day_type = day_type_for(when.date())
    moment = when.time()
    return [
        Position(bell=bell, running=bell.running(moment), upcoming=bell.upcoming(moment))
        for bell in wing_bells(wing, day_type, table)
    ]

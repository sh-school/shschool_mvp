"""شبكةُ التفريغ: أسبوعُ المعلّم خانةً خانة، ومعه ما تسعه قيودُه.

الاستمارةُ القديمةُ تضرب مصفوفة: (الأيّامُ المختارة) × (الحصصُ المختارة). فلا
سبيلَ فيها إلى «الأحدَ الأولى والاثنينَ الثالثة» — اختيارُ اليومين والحصّتين
يُنتج أربعَ خاناتٍ لا اثنتين. ولهذا سكنت قيودُ معلّمٍ واحدٍ عشرين تفريغاً
منفصلاً: عشرون سجلّاً لتعبيرٍ واحدٍ لم تحمله الاستمارة.

فهنا الأسبوعُ شبكةٌ خاليةٌ تُظلَّل خانةً خانة، ومعها شيئان لا يُتّخذ القرارُ
بدونهما:

  1. **التفريغُ القائم** — يُعرض مظلّلاً فلا يُطلب مرّتين.
  2. **إمكانيّةُ التفريغ** — وقاعدتُها صريحة (قرارُ المستخدم 2026-09-09):

         خاناتُ الأسبوع − نصابُ المعلّم = ما يجوز تفريغُه

     وخاناتُ الأسبوع ليست خمساً وثلاثين دائماً: سابعةُ الخميس لا وجودَ لها
     لمن لا يُدرّس ثانويّاً، فتُطرح من العدّ لا تُحسب فرصةً.

     ومعها سطرٌ ثانويّ: ما تسعه تفضيلاتُ المعلّم (`weekly_capacity` — الدالّةُ
     نفسُها التي تحرس صفحةَ التفضيلات) حين تكون أضيقَ من الحدّ الصريح، فسقفٌ
     يوميٌّ منخفضٌ يضيّق ما لا تضيّقه القسمةُ وحدَها.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field

from operations.models import ScheduleSlot

#: أيّامُ الأسبوع وحصصُه — من النموذج لا من رقمٍ محفورٍ هنا.
DAYS = ScheduleSlot.DAYS
PERIODS = ScheduleSlot.PERIODS


@dataclass
class Cell:
    """خانةُ أسبوعٍ واحدة: أمفرَّغةٌ هي، وهل تقبل التفريغ.

    ولا تحمل شاغلَها: الشبكةُ أداةُ تفريغٍ لا عرضٌ للجدول (قرارُ المستخدم
    2026-09-09). فمن أراد جدولَ المعلّم فله شاشتُه، وهنا يُظلَّل المفرَّغُ
    وحدَه على أرضيّةٍ خالية.
    """

    day: int
    period: int
    #: معرّفُ تفريغٍ قائمٍ على هذه الخانة — فلا تُختار مرّتين.
    exemption_id: str = ""
    #: أهو تفريغُ «يومٍ كامل»؟ فلا يُرفع بخانةٍ واحدةٍ بل بصفّه.
    from_full_day: bool = False
    #: خانةٌ لا وجودَ لها في أسبوع هذا المعلّم — كسابعةِ الخميس لمن لا
    #: يُدرّس ثانويّاً. تُعرض مطفأةً ولا تُظلَّل.
    disabled: bool = False

    @property
    def key(self) -> str:
        return f"{self.day}:{self.period}"


@dataclass
class DayRow:
    day: int
    name: str
    cells: list[Cell] = field(default_factory=list)
    #: تفريغُ يومٍ كاملٍ قائمٌ على هذا اليوم — معرّفُه، وإلّا فارغ.
    full_day_id: str = ""


@dataclass
class GridView:
    rows: list[DayRow]
    #: نصابُ المعلّم من الإسناد — لا من الجدول، فالإسنادُ أصلُه.
    load: int
    #: ما تسعه قيودُه بعد التفريغات القائمة.
    capacity: int
    #: خاناتُ التفريغ القائمة (يومُ الكامل يُحسب بخاناته).
    blocked: int
    #: الخاناتُ الحرّةُ الآن — قائمةً ولا مفرَّغةً ولا معطّلة.
    free: int = 0
    #: خاناتُ أسبوعِ هذا المعلّم — بعد طرحِ ما لا وجودَ له في أسبوعه.
    week_slots: int = 0

    @property
    def allowance(self) -> int:
        """ما يجوز تفريغُه: خاناتُ الأسبوع ناقصَ النصاب."""
        return max(0, self.week_slots - self.load)

    @property
    def remaining(self) -> int:
        """ما بقي منها بعد التفريغ القائم."""
        return max(0, self.allowance - self.blocked)

    @property
    def margin(self) -> int:
        """الهامش الأضيق: ما تسعه التفضيلات ناقصَ النصاب — سطرٌ ثانويّ."""
        return self.capacity - self.load

    @property
    def level(self) -> str:
        """حالُ ما بقي: واسعٌ أو ضيّقٌ أو مستنفَد — تقرؤها الشاشةُ لوناً."""
        if self.remaining <= 0:
            return "impossible"
        if self.remaining <= 2:
            return "tight"
        return "ok"


def _max_period_for(day: int, level_types: set[str]) -> int:
    """أوسعُ سقفٍ ليومٍ عند من يُدرّس هذه المراحل.

    السقفُ صفةُ الشعبة لا المعلّم: الخميسُ ستُّ حصصٍ في الإعداديّ وسبعٌ في
    الثانويّ. ومن يُدرّس المرحلتين له السابعةُ الخميسيّةُ مشروعةً في شعبةٍ
    ثانويّة — فيُؤخذ الأوسعُ لا الأضيق، وإلّا حُجبت عنه خانةٌ يعمل فيها.
    """
    from operations.scheduler_constraints import get_max_periods_for_day

    if not level_types:
        return max(PERIODS)
    return max(get_max_periods_for_day(day, level) for level in level_types)


def build_grid(school, teacher, academic_year: str) -> GridView:
    """يبني شبكةَ أسبوعِ معلّمٍ بعينه: تفريغُ كلّ خانةٍ وسعتُه مقابلَ نصابه."""
    from operations.models import (
        SubjectClassAssignment,
        TeacherExemption,
        TeacherPreference,
    )
    from operations.preference_capacity import weekly_capacity

    exemptions = TeacherExemption.objects.filter(
        school=school, academic_year=academic_year, teacher=teacher, is_active=True
    )
    per_slot: dict[tuple[int, int], str] = {}
    full_days: dict[int, str] = {}
    for ex in exemptions:
        if ex.exemption_type == "full_day" or ex.period_number is None:
            full_days[ex.day_of_week] = str(ex.id)
        else:
            per_slot[(ex.day_of_week, ex.period_number)] = str(ex.id)

    #: مراحلُ الشُّعب التي يُدرّسها — منها سقفُ يومه.
    level_types = {
        lt
        for lt in SubjectClassAssignment.objects.filter(
            school=school, academic_year=academic_year, teacher=teacher, is_active=True
        ).values_list("class_group__level_type", flat=True)
        if lt
    }

    rows: list[DayRow] = []
    free_per_day: dict[int, int] = defaultdict(int)
    blocked = 0
    week_slots = 0
    for day, name in DAYS:
        max_p = _max_period_for(day, level_types)
        row = DayRow(day=day, name=name, full_day_id=full_days.get(day, ""))
        for period in PERIODS:
            cell = Cell(day=day, period=period, disabled=period > max_p)
            if row.full_day_id:
                cell.exemption_id = row.full_day_id
                cell.from_full_day = True
            elif (day, period) in per_slot:
                cell.exemption_id = per_slot[(day, period)]
            if not cell.disabled:
                week_slots += 1
                if cell.exemption_id:
                    blocked += 1
                else:
                    free_per_day[day] += 1
            row.cells.append(cell)
        rows.append(row)

    load = (
        sum(
            SubjectClassAssignment.objects.filter(
                school=school, academic_year=academic_year, teacher=teacher, is_active=True
            ).values_list("weekly_periods", flat=True)
        )
        or 0
    )

    pref = TeacherPreference.objects.filter(
        school=school, academic_year=academic_year, teacher=teacher
    ).first()
    capacity = weekly_capacity(
        max_daily=pref.max_daily_periods if pref else max(PERIODS),
        max_consecutive=pref.max_consecutive if pref else max(PERIODS),
        max_gap=pref.max_gap if pref else None,
        free_day=pref.free_day if pref else None,
        free_per_day=dict(free_per_day),
    )
    return GridView(
        rows=rows,
        load=load,
        capacity=capacity,
        blocked=blocked,
        free=sum(free_per_day.values()),
        week_slots=week_slots,
    )


def cells_of(grid: GridView, day: int, period: int | None) -> list[Cell]:
    """خاناتُ زوجٍ واحد — و«يومٌ كامل» (`period is None`) خاناتُ صفِّه كلِّها.

    يقرؤها حارسُ السعة: عددُ ما سيُفرَّغ فعلاً لا عددُ ما طُلب، فالمفرَّغُ
    سلفاً والمعطَّلُ لا يُنقصان سعةً مرّتين.
    """
    for row in grid.rows:
        if row.day != day:
            continue
        if period is None:
            return list(row.cells)
        return [cell for cell in row.cells if cell.period == period]
    return []


def parse_slots(raw: list[str]) -> list[tuple[int, int | None]]:
    """«يوم:حصّة» نصّاً إلى أزواجٍ صحيحة — و«يوم:*» يومٌ كامل.

    والتمييزُ ليس ترفاً: `build_tasks` يقرأ أيّامَ التفريغ من `full_day`
    وحدَها، ومنها يُنقص مقامَ قسمة النصاب على الأيّام. فسبعُ خاناتٍ مفردةٍ
    في صفٍّ واحدٍ تُفرّغ اليومَ في الشبكة **ولا تُعَدّ يوماً فارغاً في
    الحساب** — فيقسم المولّدُ النصابَ على خمسةٍ ويصطدم بلا سببٍ ظاهر.

    والمدخلُ من المتصفّح فلا يُوثق به: ما ليس على الصيغة أو خرج عن المدى
    يُهمَل، ولا تسقط الصفحةُ بـ500. ويومٌ كاملٌ يبتلع خاناتِه المفردة فلا
    تُسجَّل مرّتين.
    """
    days = {d for d, _ in DAYS}
    pairs: list[tuple[int, int | None]] = []
    seen: set[tuple[int, int | None]] = set()
    whole: set[int] = set()
    for item in raw:
        part = (item or "").strip().split(":")
        if len(part) != 2:
            continue
        try:
            day = int(part[0])
        except ValueError:
            continue
        if day not in days:
            continue
        if part[1].strip() == "*":
            whole.add(day)
            key: tuple[int, int | None] = (day, None)
        else:
            try:
                period = int(part[1])
            except ValueError:
                continue
            if period not in PERIODS:
                continue
            key = (day, period)
        if key in seen:
            continue
        seen.add(key)
        pairs.append(key)
    #: اليومُ الكاملُ يغني عن خاناته — وإلّا سُجّل التفريغُ مرّتين بوجهين.
    pairs = [p for p in pairs if p[1] is None or p[0] not in whole]
    return sorted(pairs, key=lambda p: (p[0], -1 if p[1] is None else p[1]))

"""operations/services/schedule_week.py — أسبوعٌ فعليّ من حصص الأيّام (الجدول الديناميكيّ).

الجدولُ الأسبوعيّ كان يقرأ `ScheduleSlot` وحدَها: الخطّةَ المعتمدة. فالإشغالُ والتبديلُ والتعويضُ
— وكلُّها تقع على `Session` ليومٍ بعينه لا على القالب — لا تظهر فيه أبداً، ولا إجازةُ الطلبة، ولا
تعاقبُ الأسابيع. وقد صار رقمُ الحصّة محفوظاً في `Session` (`period_number`)، فيمكن أن تُبنى الورقةُ
نفسُها من الحصص الفعليّة.

قراراتُ المالك (2026-09-25) لهذا القارئ:
- الأسبوعُ الفعليّ هو الافتراضيّ، والخطّةُ المعتمدةُ خيارٌ يبقى.
- أسبوعٌ (أو يومٌ) لم يُولَّد بعدُ يُعرض **من الخطّة** ويُوسَم `source == "plan"` — فلا يُترك فارغاً.
  ولا كتابةَ في القاعدة من القراءة: التوليدُ عند الطلب يُنشئ حصصاً، وهذه قراءةٌ محضة.
- ويومُ إجازةِ الطلبة لا خانةَ فيه، ويُسمّى سببُ إغلاقه.

وشكلُ الخانة كشكل `ScheduleSlot` حرفاً (`teacher`، `class_group`، `subject`، `day_of_week`،
`period_number`، `start_time`، `end_time`) — فتقرؤها الشبكةُ والورقةُ وPDF وExcel بلا تغيير. وتُزاد
عليها ثلاثُ صفات: `kind` (`""` أو `swap` أو `cover` أو `comp`)، و`original_teacher`، و`source`
(`actual` أو `plan`) — لتلوين الخانة وذكر «عن فلان». وهي غلافٌ (`LessonCell`) يفوّض ما لا يعرّفه
إلى الحصّة أو الخانة الأصليّة: لا يُعدَّل كائنُ نموذجٍ في الذاكرة ليحمل ما ليس من حقوله.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import TYPE_CHECKING, Any

from core.academic_calendar import academic_year_for_school
from operations.models import ScheduleSlot, Session, TimeSlotConfig
from operations.school_days import SchoolDays, school_day

if TYPE_CHECKING:
    from core.models import ClassGroup, CustomUser, School

#: أيّامُ الدوام: أحد … خميس.
DAYS = 5

#: ما يُكتب في الخانة لمن حُوّلت حصّتُه — بنصوص «حصصي اليوم» نفسِها فلا يقرأ المعلّمُ لغتين.
KIND_NOTES = {
    "swap": "تبديل — كانت لـ{}",
    "cover": "إشغال — عن {}",
    "comp": "تعويض — في حصّة {}",
}
#: وسمُ كلّ نوعٍ في مفتاح الألوان، بترتيب عرضه.
KIND_LABELS = {"cover": "إشغال", "swap": "تبديل", "comp": "تعويض"}


class LessonCell:
    """خانةٌ في أسبوعٍ فعليّ — تلفّ `Session` (فعليّة) أو `ScheduleSlot` (من الخطّة).

    ما لا تعرّفه تفوّضه إلى الأصل: `teacher`، `class_group`، `subject`، `start_time`،
    `end_time`، `elective_group`… فتقرؤها القوالبُ كما تقرأ الخانة.
    """

    def __init__(
        self,
        lesson: Any,
        *,
        day_of_week: int,
        period_number: int,
        source: str,
        kind: str = "",
        original_teacher: Any = None,
    ) -> None:
        self._lesson = lesson
        self.day_of_week = day_of_week
        self.period_number = period_number
        #: `actual` من حصص الأيّام، أو `plan` من الخطّة المعتمدة (لم يُولَّد اليومُ بعد).
        self.source = source
        #: `""` أو `swap` أو `cover` أو `comp`.
        self.kind = kind
        self.original_teacher = original_teacher
        #: تسميةُ الخانة المشتركة في جدول المعلّم — يضبطها القارئُ.
        self.cell_subject = ""

    @property
    def note(self) -> str:
        """سطرُ الخانة «إشغال — عن فلان» — وفارغٌ لحصّةٍ لم يُبدَّل معلّمُها."""
        who = getattr(self.original_teacher, "full_name", "")
        return KIND_NOTES[self.kind].format(who) if self.kind and who else ""

    def __getattr__(self, name: str) -> Any:
        if name == "_lesson":  # قبل أن يُضبط في `__init__` (نسخٌ أو تفريغ): لا تكرارَ لانهائيّ
            raise AttributeError(name)
        return getattr(self._lesson, name)


@dataclass
class WeekLessons:
    """حصصُ أسبوعٍ بشكل الخانة، مع ما يلزم القارئَ ليشرح ما يعرض."""

    week_start: date
    days: list[date]
    lessons: list[LessonCell] = field(default_factory=list)
    #: يومٌ (0 … 4) ← سببُ إغلاقه: إجازةُ الطلبة أو ما قبل بدء الدوام.
    closed: dict[int, str] = field(default_factory=dict)
    #: أيّامٌ لم تُولَّد حصصُها بعد فعُرضت من الخطّة المعتمدة.
    plan_days: set[int] = field(default_factory=set)
    #: حصصٌ لا يُعرف رقمُها (خانتُها لم تعد نشطةً ولا جرسَ يطابق وقتَها) فلم تُوضَع.
    unplaced: int = 0

    @property
    def week_end(self) -> date:
        return self.days[-1]


def _day_type(day_index: int) -> str:
    """نوعُ جرس اليوم: الخميسُ (4) جرسُه غيرُ جرس الأحد–الأربعاء."""
    return "thursday" if day_index == 4 else "regular"


def _bells(school: School) -> dict[tuple[Any, str, Any], int]:
    """(نطاق، نوعُ اليوم، بدايةُ الحصّة) → رقمُها — لحصصٍ سبقت الحقلَ ولم تُعبَّأ في الهجرة 0059."""
    rows = TimeSlotConfig.objects.filter(school=school, is_break=False).values_list(
        "band_id", "day_type", "start_time", "period_number"
    )
    return {(band, kind, start): period for band, kind, start, period in rows}


def _kinds(sessions: list[Session]) -> dict[Any, str]:
    """ما بُدّل معلّمُه من حصص الأسبوع: تعويضٌ أو إشغالٌ أو تبديل — والباقي لا علامةَ له.

    ثلاثتُها تكتب `original_teacher`؛ يُفرَّق بينها بسجلّاتها (`CompensatoryService.session_ids`،
    `SubstituteService.cover_session_ids`) — استعلامان لا استعلامٌ لكلّ حصّة.
    """
    from operations.services.compensatory import CompensatoryService
    from operations.services.substitute import SubstituteService

    moved = [s for s in sessions if s.original_teacher_id]
    if not moved:
        return {}
    comp = CompensatoryService.session_ids(moved)
    cover = SubstituteService.cover_session_ids(moved)
    return {s.pk: "comp" if s.pk in comp else "cover" if s.pk in cover else "swap" for s in moved}


def week_lessons(
    school: School,
    week_start: date,
    academic_year: str | None = None,
    teacher: CustomUser | None = None,
    class_group: ClassGroup | None = None,
) -> WeekLessons:
    """حصصُ الأسبوع الذي فيه `week_start` (أحدُه إلى خميسه) — فعليّةً حيثُ وُلّدت، ومن الخطّة حيثُ لم تُولَّد.

    و`teacher` يُصفّي على **حامل** الحصّة اليومَ: من أُشغل عنه لا تظهر عنده، ومن أُشغل مكانَه تظهر
    عنده بعلامتها. و`class_group` على الشعبة. والاستعلاماتُ ثابتةُ العدد مهما كثرت الحصص.
    """
    from operations.services.schedule import ScheduleService

    sunday, thursday = ScheduleService._get_week_bounds(week_start)
    days = [sunday + timedelta(days=i) for i in range(DAYS)]
    year = academic_year or academic_year_for_school(school, on=sunday)
    week = WeekLessons(week_start=sunday, days=days)

    school_days = SchoolDays(school, sunday, thursday)
    week.closed = {
        i: school_day(school, day).closed_reason
        for i, day in enumerate(days)
        if day not in school_days
    }

    everything = Session.objects.filter(
        school=school, date__range=(sunday, thursday), class_group__academic_year=year
    )
    # «وُلّد اليومُ؟» سؤالٌ عن المدرسة كلّها لا عن هذا المعلّم: معلّمٌ بلا حصّةٍ يومَ الثلاثاء
    # لا يعني أنّ الثلاثاء لم يُولَّد.
    generated = set(everything.order_by().values_list("date", flat=True).distinct())
    scoped = everything
    if teacher is not None:
        scoped = scoped.filter(teacher=teacher)
    if class_group is not None:
        scoped = scoped.filter(class_group=class_group)
    sessions = list(scoped.select_related("teacher", "class_group", "subject", "original_teacher"))

    kinds = _kinds(sessions)
    bells: dict[tuple[Any, str, Any], int] | None = None
    for session in sessions:
        day_index = ScheduleService._PY_TO_QATAR.get(session.date.weekday())
        if day_index is None:
            continue
        period = session.period_number
        if period is None:
            bells = bells if bells is not None else _bells(school)
            period = bells.get(
                (session.class_group.time_band_id, _day_type(day_index), session.start_time)
            )
        if period is None:
            week.unplaced += 1
            continue
        week.lessons.append(
            LessonCell(
                session,
                day_of_week=day_index,
                period_number=period,
                source="actual",
                kind=kinds.get(session.pk, ""),
                original_teacher=session.original_teacher,
            )
        )

    week.plan_days = {
        i for i, day in enumerate(days) if day not in generated and i not in week.closed
    }
    if week.plan_days:
        slots = ScheduleSlot.objects.filter(
            school=school, academic_year=year, is_active=True, day_of_week__in=week.plan_days
        ).select_related("teacher", "class_group", "subject")
        if teacher is not None:
            slots = slots.filter(teacher=teacher)
        if class_group is not None:
            slots = slots.filter(class_group=class_group)
        week.lessons.extend(
            LessonCell(
                slot, day_of_week=slot.day_of_week, period_number=slot.period_number, source="plan"
            )
            for slot in slots
        )
    return week


class ScheduleWeekMixin:
    """مقطعٌ من `ScheduleService`: الجدولُ الأسبوعيّ من حصص الأيّام (الشبكةُ المفردةُ والجدولُ العامّ)."""

    @classmethod
    def get_week_schedule(
        cls,
        school: School,
        week_start: date,
        teacher: CustomUser | None = None,
        class_group: ClassGroup | None = None,
        academic_year: str | None = None,
    ) -> dict[str, Any]:
        """شبكةُ أسبوعٍ فعليّ: `{"grid": {يوم: {حصّة: [خانة]}}, "week": WeekLessons}`.

        الشبكةُ بشكل `get_weekly_schedule` نفسِه فتقرؤها الورقةُ بلا تغيير؛ ومعها `week` لما لا تحمله
        الشبكة: تواريخُ الأيّام، وسببُ إغلاق كلّ يومٍ مغلق، وأيّامُ الخطّة، وما لم يوضَع.
        """
        from operations.services.schedule_read import parallel_labels

        week = week_lessons(school, week_start, academic_year, teacher, class_group)
        year = academic_year or academic_year_for_school(school, on=week.week_start)
        labels = parallel_labels(school, year) if teacher is not None else None
        grid: dict[int, dict[int, list[Any]]] = {d: {} for d in range(DAYS)}
        # وداخلَ الخانة ترتيبُ المدرسة: من 7/1 إلى 12/4.
        for cell in sorted(
            week.lessons, key=lambda c: (c.class_group.school_order, c.elective_group or "")
        ):
            if labels is not None:
                cell.cell_subject = labels.get(
                    (cell.class_group_id, cell.day_of_week, cell.period_number), ""
                )
            grid[cell.day_of_week].setdefault(cell.period_number, []).append(cell)
        return {"grid": grid, "week": week}

    @classmethod
    def get_week_matrix(
        cls, school: School, week_start: date, academic_year: str | None = None
    ) -> dict[str, Any]:
        """الجدولُ العامّ لأسبوعٍ فعليّ: `{"rows": [...], "week": WeekLessons}` — صفوفُه كـ`get_teachers_matrix`."""
        week = week_lessons(school, week_start, academic_year)
        year = academic_year or academic_year_for_school(school, on=week.week_start)
        ordered = sorted(
            week.lessons,
            key=lambda c: (c.teacher.full_name or "", c.day_of_week, c.period_number),
        )
        from operations.services.schedule_read import ScheduleReadMixin

        return {"rows": ScheduleReadMixin._matrix_rows(school, year, ordered), "week": week}

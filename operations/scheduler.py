"""
scheduler.py — خوارزمية التوليد الذكية للجدول الأسبوعي
Greedy + Backtracking + Local Search
قطر
"""

from __future__ import annotations

import logging
import math
import random
import time
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import time as dt_time

from django.db import transaction

from core.models import School

from .models import (
    ScheduleGeneration,
    ScheduleSlot,
    Subject,
    SubjectClassAssignment,
    TeacherExemption,
    TeacherPreference,
    TimeSlotConfig,
)
from .scheduler_constraints import (
    calculate_quality_score,
    evaluate_soft_constraints,
    is_slot_valid,
)

logger = logging.getLogger(__name__)

#: من يُسمح له بزوجٍ متلاصقٍ واحدٍ في الأسبوع — قرارُ إدارة المدرسة.
#:
#: والشرطانِ **معاً** لا أحدُهما: معلّمُ اللغة العربيّة في شعبةٍ نصابُها ستُّ
#: حصص. فلا تدخل فيها رياضياتٌ سداسيّةٌ ولا عربيّةٌ بخمس.
ADJACENCY_ALLOWED_SUBJECTS = {"اللغة العربية"}
ADJACENCY_ALLOWED_WEEKLY = 6

#: كم محاولةً تُجرَّب قبل اختيار أفضلها.
#:
#: وتتوقّف السلسلةُ عند أوّل محاولةٍ كاملة، فالثمنُ لا يُدفع إلّا عند الحاجة:
#: بقيودٍ يسعها الجدولُ تنتهي المحاولةُ الأولى في ثانية، وبقيودٍ تضيق عنه
#: تُجرَّب الثلاثُ في نحوِ دقيقة.
RESTARTS = 3

DAYS = [0, 1, 2, 3, 4]  # أحد - خميس
#: آخرُ حصّةٍ في اليوم — لها حكمُها الخاصّ في التوزيع.
LAST_PERIOD = 7
DAY_NAMES = {0: "الأحد", 1: "الاثنين", 2: "الثلاثاء", 3: "الأربعاء", 4: "الخميس"}


@dataclass
class Member:
    """معلّمٌ ومادّةٌ داخل مهمّةٍ واحدة.

    فالمهمّةُ عادةً معلّمٌ واحدٌ ومادّةٌ واحدة، إلّا في الشعبة المنقسمة: مادّتان
    ومعلّمان في الخانة نفسها لقسمَي الطلاب.
    """

    teacher_id: str
    teacher_name: str
    subject_id: str
    subject_name: str
    subject_code: str


@dataclass
class Task:
    """مهمة جدولة: خانةٌ واحدةٌ لشعبةٍ واحدة — بمادّةٍ أو بمادّتين متوازيتين"""

    class_id: str
    class_name: str
    subject_id: str
    subject_name: str
    subject_code: str
    teacher_id: str
    teacher_name: str
    weekly_periods: int
    requires_lab: bool = False
    #: **تفضيلٌ لا اشتراط.** لا قيدَ صلباً يفرض تجاور الحصّتين؛ أثرُه
    #: عقوبةٌ مرنةٌ ترجّح التجاور وتُلغي عقوبةَ تكرار المادّة في اليوم.
    #: (وحقلُ القاعدة `Subject.requires_double_period` يحمل الاسمَ القديم.)
    prefers_double: bool = False
    preferred_periods: list = field(default_factory=list)
    level_type: str = ""  # "prep" (إعدادي) أو "sec" (ثانوي) — للخميس
    #: كم زوجاً متلاصقاً يُسمح لصاحب هذه المهمّة في الأسبوع — عن طيبِ خاطرٍ
    #: لا عن ضرورة. قرّرت الإدارةُ زوجاً واحداً لمعلّمي اللغة العربيّة ولمن
    #: نصابُه في الشعبة ستُّ حصص: نصابٌ ثقيلٌ في أسبوعٍ ضيّقٍ يصعب تفريقُه.
    adjacency_allowance: int = 0
    #: سقفُ التلاصق الخاصُّ بمعلّم هذه المهمّة — صفرٌ يعني «خُذ العامّ».
    #: والخاصُّ لا يُرفع في جولة الاسترخاء: قرارٌ في حقّ معلّمٍ بعينه أثقلُ من
    #: سقفٍ عامٍّ وُضع ليُقارَب.
    consecutive_cap: int = 0
    #: الموارد التي تستهلكها هذه المهمّة: (معرّف المورد · سعته).
    resources: tuple = ()
    #: كم خانةً متلاصقةً تشغل هذه المهمّة: واحدةً عادةً، واثنتين في المزدوجة.
    #: والمزدوجةُ مهمّةٌ واحدةٌ لا مهمّتان تلتقيان بالصدفة — فلو كانتا اثنتين
    #: لاحتاج المحرّكُ أن يعرف عند وضع الأولى أين ستقع الثانية، وهو ما لا
    #: يعرفه أحد.
    span: int = 1
    #: أيّامُ المعلّم المتاحةُ في الأسبوع — خمسةٌ ما لم يكن مفرَّغاً يوماً.
    #: وهي مقامُ القسمة في توزيع المادّة، فمعلّمٌ يعمل أربعةَ أيّامٍ يلزم
    #: مادّتَه السداسيّةَ يومان مزدوجان لا يومٌ واحد.
    available_days: int = 5
    #: وسمُ المجموعة المتوازية — فارغٌ في الغالبيّة العظمى.
    parallel_group: str = ""
    #: ساكنو الخانة: واحدٌ عادةً، واثنان في الشعبة المنقسمة. والحقولُ المفردةُ
    #: أعلاه تصف أوّلَهم، فتبقى القيودُ المرنةُ تقرأ ما كانت تقرأ.
    members: list = field(default_factory=list)

    def __post_init__(self):
        if not self.members:
            self.members = [
                Member(
                    teacher_id=self.teacher_id,
                    teacher_name=self.teacher_name,
                    subject_id=self.subject_id,
                    subject_name=self.subject_name,
                    subject_code=self.subject_code,
                )
            ]

    @property
    def is_split(self) -> bool:
        return len(self.members) > 1

    def slots(self, period: int):
        """الخاناتُ التي تشغلها هذه المهمّةُ ابتداءً من هذه الحصّة."""
        return range(period, period + self.span)

    @property
    def per_day_cap(self) -> int:
        """أكثرُ ما يجوز لهذه المادّة في يومٍ واحدٍ لهذه الشعبة.

            perDayCap = ⌈W / D⌉

        فستُّ حصصٍ على خمسة أيّامٍ سقفُها حصّتان، وعلى أربعةٍ سقفُها حصّتان
        أيضاً — والفرقُ في **عدد** الأيّام التي تبلغ السقف لا في السقف نفسه.
        """
        days = max(1, self.available_days)
        return max(1, math.ceil(self.weekly_periods / days))

    @property
    def days_allowed_at_cap(self) -> int:
        """كم يوماً يجوز أن يبلغ السقف.

            daysAtCap = W mod D    (وإن قسمت بلا باقٍ فالأيّامُ كلُّها سواء)

        فستٌّ على خمسةٍ: يومٌ واحدٌ مزدوج. وستٌّ على أربعةٍ: يومان. وخمسٌ على
        خمسةٍ: لا مزدوجَ البتّة، والأيّامُ الخمسةُ كلُّها «عند السقف» وهو واحد.
        """
        days = max(1, self.available_days)
        remainder = self.weekly_periods % days
        return remainder if remainder else days


class ScheduleGrid:
    """شبكةُ الجدول: خانةٌ لكلّ شعبةٍ في كلّ توقيت.

        SchoolCapacity = Classes × SlotsPerWeek

    كانت الشبكةُ `_grid[day][period]` — خانةً واحدةً للمدرسة بأسرها. فمتى وُضعت
    حصّةٌ في (الأحد · ح1) امتلأت الخانةُ في نظر الشُّعب كلِّها، وصار سقفُ المولّد
    خمساً وثلاثين حصّةً مهما كانت البيانات. وهذا ليس ضيقاً في القيود بل خطأٌ في
    وصف المدرسة: خمسٌ وعشرون شعبةً تعمل في التوقيت نفسه، وذلك توازٍ لا تعارض.

    فالفهرسةُ الآن بالشعبة، والتعارضُ نوعان لا واحد:

        شعبةٌ بمادّتين في التوقيت    ← تُمنع بخانة الشعبة
        معلّمٌ في شعبتين في التوقيت   ← يُمنع بفهرس المعلّم

    والتتابعُ صفةُ معلّمٍ يقطع الشُّعب، والمزاوجةُ صفةُ شعبةٍ ومادّة — فلكلٍّ
    فهرسُه.
    """

    def __init__(self):
        #: _grid[class_id][day][period] = Task
        self._grid: dict[str, dict[int, dict[int, Task | None]]] = {}
        # فهارس سريعة
        self._teacher_slots: dict[str, list[tuple[int, int]]] = defaultdict(list)
        self._class_slots: dict[str, list[tuple[int, int]]] = defaultdict(list)
        #: مَن يُدرّس لهذا المعلّم في هذا التوقيت — للتتابع وللتعارض معاً.
        self._teacher_at: dict[tuple[str, int, int], Task] = {}
        self._subject_class_day: dict[tuple[str, str, int], int] = defaultdict(int)
        #: (مادّة · شعبة · رقم الحصّة) — لتنويع مواقع المادّة في اليوم.
        self._subject_period: dict[tuple[str, str, int], int] = defaultdict(int)
        #: (مورد · يوم · حصّة) — كم حصّةً تشغله في هذا التوقيت.
        self._resource_at: dict[tuple[str, int, int], int] = defaultdict(int)
        self._entries: list[dict] = []
        #: سجلُّ التراجع: كلُّ محاولةِ إزاحةٍ تفتح إطاراً، وتُغلقه بقبولٍ أو ردّ.
        #: والردُّ يعكس ما جرى بعينه — لا «أعِد ما تظنّه كان»، فالتساهلُ في
        #: هذا أسقط حصصاً بصمتٍ حتّى صار المجموعُ لا يُطابق المطلوب.
        self._journal: list[list[tuple[str, int, int, Task]]] = []

    def _class_grid(self, class_id: str) -> dict[int, dict[int, Task | None]]:
        """شبكةُ شعبةٍ تُنشأ عند أوّل ذكرٍ لها — فالشعبُ تُعرَف من المهامّ."""
        grid = self._grid.get(class_id)
        if grid is None:
            grid = {d: dict.fromkeys(range(1, 8)) for d in DAYS}
            self._grid[class_id] = grid
        return grid

    def begin(self):
        """يفتح إطارَ تراجعٍ — كلُّ ما يقع بعده يُسجَّل."""
        self._journal.append([])

    def commit(self):
        """يقبل ما جرى: يُدمَج في الإطار الأعلى إن وُجد، وإلّا يُنسى."""
        done = self._journal.pop()
        if self._journal:
            self._journal[-1].extend(done)

    def rollback(self):
        """يعكس ما جرى في الإطار — بالترتيب المقلوب."""
        for kind, day, period, task in reversed(self._journal.pop()):
            if kind == "place":
                self._forget(task, day, period)
            else:
                self._remember(day, period, task)

    def _log(self, kind: str, day: int, period: int, task: Task):
        if self._journal:
            self._journal[-1].append((kind, day, period, task))

    def place(self, day: int, period: int, task: Task):
        """وضع حصة في الشبكة"""
        self._log("place", day, period, task)
        self._remember(day, period, task)

    def _remember(self, day: int, period: int, task: Task):
        for slot in task.slots(period):
            self._class_grid(task.class_id)[day][slot] = task
            self._class_slots[task.class_id].append((day, slot))
            for member in task.members:
                self._teacher_slots[member.teacher_id].append((day, slot))
                self._teacher_at[(member.teacher_id, day, slot)] = task
            self._subject_class_day[(task.subject_id, task.class_id, day)] += 1
            self._subject_period[(task.subject_id, task.class_id, slot)] += 1
            for resource_id, _ in task.resources:
                self._resource_at[(resource_id, day, slot)] += 1
        self._entries.append({"day": day, "period": period, "task": task})

    def remove(self, class_id: str, day: int, period: int):
        """إزالةُ حصّةِ شعبةٍ بعينها — ولا تمسّ جاراتِها في التوقيت نفسه."""
        task = self._class_grid(class_id)[day][period]
        if task is None:
            return
        start = self._start_of(task, day, period)
        self._log("remove", day, start, task)
        self._forget(task, day, start)

    def _start_of(self, task: Task, day: int, period: int) -> int:
        """موضعُ بداية المهمّة — فالمزدوجةُ تُرفع من أوّلها لا من نصفها."""
        start = period
        while start > 1 and self._class_grid(task.class_id)[day].get(start - 1) is task:
            start -= 1
        return start

    def _forget(self, task: Task, day: int, period: int):
        start = self._start_of(task, day, period)
        for slot in task.slots(start):
            self._class_grid(task.class_id)[day][slot] = None
            self._class_slots[task.class_id].remove((day, slot))
            for member in task.members:
                self._teacher_slots[member.teacher_id].remove((day, slot))
                self._teacher_at.pop((member.teacher_id, day, slot), None)
            self._subject_class_day[(task.subject_id, task.class_id, day)] -= 1
            self._subject_period[(task.subject_id, task.class_id, slot)] -= 1
            for resource_id, _ in task.resources:
                self._resource_at[(resource_id, day, slot)] -= 1
        self._entries = [e for e in self._entries if e["task"] is not task]

    # ── الإشغال: سؤالان مختلفان ───────────────────────────────────

    def teacher_busy(self, teacher_id: str, day: int, period: int) -> bool:
        """هل هذا المعلّمُ مشغولٌ في هذا التوقيت — في أيّ شعبةٍ كانت؟"""
        return (teacher_id, day, period) in self._teacher_at

    def class_busy(self, class_id: str, day: int, period: int) -> bool:
        """هل لهذه الشعبة حصّةٌ في هذا التوقيت؟"""
        return self._class_grid(class_id)[day][period] is not None

    def teacher_task_at(self, teacher_id: str, day: int, period: int) -> Task | None:
        return self._teacher_at.get((teacher_id, day, period))

    def teacher_periods_on_day(self, teacher_id: str, day: int) -> int:
        """عدد حصص المعلم في يوم"""
        return sum(1 for d, p in self._teacher_slots[teacher_id] if d == day)

    def class_periods_on_day(self, class_id: str, day: int) -> int:
        """عدد حصص الفصل في يوم"""
        return sum(1 for d, p in self._class_slots[class_id] if d == day)

    def subject_on_day(self, class_id: str, subject_id: str, day: int) -> int:
        """عدد حصص مادة لفصل في يوم"""
        return self._subject_class_day.get((subject_id, class_id, day), 0)

    def subject_at_period(self, class_id: str, subject_id: str, period: int) -> int:
        """كم مرّةً وقعت هذه المادّةُ في هذه الحصّة من اليوم خلال الأسبوع.

        فمادّةٌ كلُّ حصصها في الحصّة الخامسة جدولٌ لا يقبله أحد: الطالبُ يلقاها
        في التوقيت نفسه كلَّ يوم، والمعلّمُ كذلك. والتنوّعُ مقصودٌ لا مصادفة.
        """
        return self._subject_period.get((subject_id, class_id, period), 0)

    def resource_load(self, resource_id: str, day: int, period: int) -> int:
        """كم حصّةً تشغل هذا المورد في هذا التوقيت — ملعباً كان أو معملاً."""
        return self._resource_at.get((resource_id, day, period), 0)

    def teacher_adjacent_pairs(self, teacher_id: str) -> int:
        """كم زوجاً متلاصقاً لهذا المعلّم في الأسبوع كلِّه.

        يُحسب على الخانات لا على المهامّ، فالمزدوجةُ المقصودةُ تُعدّ زوجاً —
        وهي كذلك في نظر المعلّم: حصّتان يقفهما متتاليتين.
        """
        by_day = defaultdict(list)
        for day, period in self._teacher_slots[teacher_id]:
            by_day[day].append(period)
        pairs = 0
        for periods in by_day.values():
            ordered = sorted(periods)
            pairs += sum(
                1 for i in range(1, len(ordered)) if ordered[i] == ordered[i - 1] + 1
            )
        return pairs

    def teacher_last_periods(self, teacher_id: str) -> int:
        """كم حصّةً سابعةً لهذا المعلّم في الأسبوع."""
        return sum(1 for _, period in self._teacher_slots[teacher_id] if period == LAST_PERIOD)

    def teacher_consecutive_counted(self, teacher_id: str, day: int, period: int) -> int:
        """تتابعُ المعلّم عبر الشُّعب — و`PE`/`SCI` تُعيد العدّاد.

        والتتابعُ صفةُ معلّمٍ لا صفةُ شعبة: حصّتان متتاليتان في شعبتين
        مختلفتين تتابعٌ يُتعب صاحبَه كما يُتعبه التتابعُ في شعبةٍ واحدة.
        """
        from .scheduler_constraints import CONSECUTIVE_RESET_CODES

        count = 0
        for step in (-1, 1):
            p = period + step
            while 1 <= p <= 7:
                task = self.teacher_task_at(teacher_id, day, p)
                if task is None or task.subject_code in CONSECUTIVE_RESET_CODES:
                    break
                count += 1
                p += step
        return count

    def would_create_gap(self, teacher_id: str, day: int, period: int) -> bool:
        """هل إضافة حصة ستخلق فجوة للمعلم؟"""
        periods_today = sorted(p for d, p in self._teacher_slots[teacher_id] if d == day)
        periods_today.append(period)
        periods_today.sort()
        if len(periods_today) < 2:
            return False
        for i in range(len(periods_today) - 1):
            diff = periods_today[i + 1] - periods_today[i]
            # فجوة إذا الفرق > 1 (مع مراعاة الاستراحات)
            if diff > 2:
                return True
        return False

    def all_entries(self) -> list[dict]:
        return self._entries

    def get_task_at(self, class_id: str, day: int, period: int) -> Task | None:
        """ساكنُ خانةِ شعبةٍ بعينها — تقرؤه المزاوجةُ وتوزيعُ المادّة."""
        return self._class_grid(class_id)[day][period]


def build_tasks(school: School, academic_year: str) -> list[Task]:
    """بناء قائمة المهام من SubjectClassAssignment"""
    # تحميل المواد التي تتطلب حصة مزدوجة (من إعدادات النائب الأكاديمي)
    double_period_subjects = set(
        Subject.objects.filter(school=school, requires_double_period=True).values_list(
            "id", flat=True
        )
    )

    assignments = SubjectClassAssignment.objects.filter(
        school=school, academic_year=academic_year, is_active=True
    ).select_related("class_group", "subject", "teacher")

    from operations.models import SchedulingResource, TeacherExemption, TeacherPreference

    # سقوفُ التلاصق الخاصّة — حقلٌ في `TeacherPreference` كان يُحمَّل ولا
    # يُستعمَل قطّ، شأنَ `requires_double_period` قبله.
    personal_cap = {
        str(p.teacher_id): p.max_consecutive
        for p in TeacherPreference.objects.filter(school=school, academic_year=academic_year)
        if p.max_consecutive
    }

    # أيّامُ التفريغ الكاملة لكلّ معلّم — مقامُ القسمة في التوزيع.
    # ومواردُ المدرسة المحدودة: أيُّ مادّةٍ تستهلك أيَّ موردٍ وبأيّ سعة.
    resources_by_subject = defaultdict(list)
    for resource in SchedulingResource.objects.filter(
        school=school, is_active=True
    ).prefetch_related("subjects"):
        for subject in resource.subjects.all():
            resources_by_subject[str(subject.id)].append((str(resource.id), resource.capacity))

    exempt_days = defaultdict(set)
    for ex in TeacherExemption.objects.filter(
        school=school, academic_year=academic_year, is_active=True, exemption_type="full_day"
    ):
        exempt_days[str(ex.teacher_id)].add(ex.day_of_week)

    rows = []
    for a in assignments:
        # تجاوز المواد التي لم يُعيّن لها معلم بعد
        if not a.teacher_id or a.teacher is None:
            continue

        # المرحلةُ تُقرأ من الشعبة ولا تُشتقّ من الصفّ.
        #
        # كان هنا `if grade in (7, 8, 9)` و`ClassGroup.grade` نصٌّ («G7»…«G12»)
        # لا عدد، فلا تصدق المقارنةُ أبداً ويخرج `level_type` فارغاً لكلّ شعبةٍ
        # في المدرسة. وأثرُه أنّ `get_max_periods_for_day` يأخذ الخميسَ بالأضيق
        # — ستُّ حصصٍ — للثانويّ أيضاً، فيخسر حصّتَه السابعة ويضيق الجدولُ من
        # حيث لا يُرى: لا تعارضَ ظاهرٌ، بل طاقةٌ أقلُّ وحصصٌ تتعذّر.
        #
        # و`ClassGroup.level_type` حقلٌ قائمٌ يحمل «prep»/«sec»، فيُقرأ ولا
        # يُعاد اشتقاقُه: اشتقاقٌ ثانٍ لحقيقةٍ محفوظةٍ يفترق عنها يوماً.
        level_type = a.class_group.level_type or ""

        # حصة مزدوجة: من إعدادات المادة في DB أو من الكود القديم
        is_double = a.subject_id in double_period_subjects or a.subject.code in {"ART", "TECH"}

        available = len(DAYS) - len(exempt_days.get(str(a.teacher_id), ()))
        rows.append((a, level_type, is_double, max(1, available)))

    return _to_tasks(rows, resources_by_subject, personal_cap)


def _to_tasks(rows, resources_by_subject=None, personal_cap=None) -> list[Task]:
    """يحوّل الإسنادات إلى مهامّ — والمتوازيةُ منها مهمّةٌ واحدةٌ بساكنَين.

    فالشعبةُ المنقسمةُ تأخذ مادّتين في التوقيت نفسه، فلو صارتا مهمّتين لطلب
    المحرّكُ خانتين ولوقع في تعارضِ «شعبةٌ في مادّتين» — وهو تعارضٌ لا وجودَ
    له في الواقع.
    """
    from collections import defaultdict as _dd

    def member(a):
        return Member(
            teacher_id=str(a.teacher_id),
            teacher_name=a.teacher.full_name,
            subject_id=str(a.subject_id),
            subject_name=a.subject.name_ar,
            subject_code=a.subject.code,
        )

    resources_by_subject = resources_by_subject or {}
    personal_cap = personal_cap or {}

    def build(a, level_type, is_double, members, available):
        #: المهمّةُ المنقسمةُ تستهلك مواردَ ساكنيها جميعاً.
        used = []
        for member in members:
            for entry in resources_by_subject.get(member.subject_id, ()):
                if entry not in used:
                    used.append(entry)
        return Task(
            class_id=str(a.class_group_id),
            class_name=str(a.class_group),
            subject_id=str(a.subject_id),
            subject_name=a.subject.name_ar,
            subject_code=a.subject.code,
            teacher_id=str(a.teacher_id),
            teacher_name=a.teacher.full_name,
            weekly_periods=a.weekly_periods,
            requires_lab=a.requires_lab,
            prefers_double=is_double,
            preferred_periods=a.preferred_periods or [],
            level_type=level_type,
            available_days=available,
            #: زوجٌ واحدٌ مسموحٌ لمعلّمي العربيّة ولأصحاب النصاب السداسيّ.
            adjacency_allowance=(
                1
                if (
                    a.subject.name_ar in ADJACENCY_ALLOWED_SUBJECTS
                    and a.weekly_periods == ADJACENCY_ALLOWED_WEEKLY
                )
                else 0
            ),
            #: أضيقُ سقفٍ بين ساكني المهمّة — فالمنقسمةُ يحكمها أشدُّ معلّمَيها.
            consecutive_cap=min(
                (personal_cap[m.teacher_id] for m in members if m.teacher_id in personal_cap),
                default=0,
            ),
            resources=tuple(used),
            parallel_group=(a.parallel_group or "").strip(),
            members=members,
        )

    grouped = _dd(list)
    tasks = []
    for a, level_type, is_double, available in rows:
        label = (a.parallel_group or "").strip()
        if label:
            grouped[(str(a.class_group_id), label)].append((a, level_type, is_double, available))
            continue
        if is_double and a.weekly_periods >= 2:
            # المزدوجةُ مهمّةٌ واحدةٌ تشغل خانتين — ونصابٌ فرديٌّ يترك حصّةً
            # مفردةً في آخره، وهي حالةٌ مشروعةٌ لا تُقسَر على زوج.
            for _ in range(a.weekly_periods // 2):
                task = build(a, level_type, is_double, [member(a)], available)
                task.span = 2
                tasks.append(task)
            for _ in range(a.weekly_periods % 2):
                tasks.append(build(a, level_type, is_double, [member(a)], available))
            continue
        for _ in range(a.weekly_periods):
            tasks.append(build(a, level_type, is_double, [member(a)], available))

    for entries in grouped.values():
        members = [member(a) for a, _, _, _ in entries]
        lead, level_type, is_double, _ = entries[0]
        # المجموعةُ المتوازيةُ تأخذ أضيقَ أيّامِ أعضائها: من فُرّغ يومان
        # فأيّامُ المجموعةِ أيّامُه.
        available = min(av for _, _, _, av in entries)
        # الخاناتُ بأكبرِ نصابٍ في المجموعة: لو كانت الفنونُ حصّتين
        # والتكنولوجيا ثلاثاً فالخاناتُ ثلاث.
        slots = max(a.weekly_periods for a, _, _, _ in entries)
        # والمجموعةُ المزدوجةُ تُزدوَج كغيرها: تكنولوجيا الحادي عشر/1 حصّتان
        # متلاصقتان وإن شاركتها الفنونُ في التوقيت نفسه. وكانت تُبنى مفردةً
        # لأنّ الازدواجَ كان مقصوراً على غير المتوازي.
        if is_double and slots >= 2:
            for _ in range(slots // 2):
                task = build(lead, level_type, is_double, list(members), available)
                task.span = 2
                tasks.append(task)
            for _ in range(slots % 2):
                tasks.append(build(lead, level_type, is_double, list(members), available))
            continue
        for _ in range(slots):
            tasks.append(build(lead, level_type, is_double, list(members), available))

    return tasks


def sort_tasks(tasks: list[Task]) -> list[Task]:
    """ترتيب المهام: الأصعب أولاً (Most Constrained First)"""
    # عد كم معلم فريد لكل مادة
    subject_teacher_count = defaultdict(set)
    for t in tasks:
        subject_teacher_count[t.subject_id].add(t.teacher_id)

    def priority(task: Task) -> tuple:
        teacher_count = len(subject_teacher_count[task.subject_id])
        return (
            teacher_count,  # معلم وحيد أولاً (1 < 2 < ...)
            -task.weekly_periods,  # نصاب أعلى أولاً
            -int(task.requires_lab),  # المعامل أولاً
        )

    return sorted(tasks, key=priority)


def get_available_slots(
    grid: ScheduleGrid,
    task: Task,
    blocked_slots: set[tuple[str, int, int | None]] | None = None,
    school=None,
    allow_adjacent: bool = False,
    allow_dense: bool = False,
) -> list[tuple[int, int]]:
    """الخانات المتاحة (تحقق قيود صلبة + تفريغات + كتلة المزدوجة)"""
    from .scheduler_constraints import get_max_periods_for_day, joinable_pairs

    available = []
    level_type = getattr(task, "level_type", "")
    #: الحصّةُ المزدوجةُ لا تقطعها فسحةٌ ولا صلاة — والكتلُ من جرس المدرسة.
    pairs = joinable_pairs(school) if task.span > 1 and school is not None else None

    for day in DAYS:
        max_p = get_max_periods_for_day(day, level_type)
        for period in range(1, max_p - task.span + 2):
            slots = list(task.slots(period))
            if pairs is not None and tuple(slots) not in pairs:
                continue
            if any(grid.class_busy(task.class_id, day, slot) for slot in slots):
                continue
            if blocked_slots and any(
                (m.teacher_id, day, slot) in blocked_slots
                for m in task.members
                for slot in slots
            ):
                continue
            if any(
                grid.teacher_busy(m.teacher_id, day, slot)
                for m in task.members
                for slot in slots
            ):
                continue
            if all(
                is_slot_valid(grid, day, slot, task, allow_adjacent, allow_dense)
                for slot in slots
            ):
                available.append((day, period))
    return available


def rank_slots(
    grid: ScheduleGrid,
    task: Task,
    available: list[tuple[int, int]],
    preferences: dict | None = None,
    rng=None,
) -> list[tuple[int, int, float]]:
    """ترتيب الخانات حسب أقلّ عقوباتٍ مرنة — والمتساوياتُ تُخلط.

    والخلطُ ليس زينة: الخاناتُ المتساويةُ في العقوبة كثيرة، وترتيبُها الثابتُ
    يجعل المحرّكَ يسلك الطريقَ نفسَه في كلّ محاولة. فإن أفضى إلى انسدادٍ أفضى
    إليه دائماً — ولو أُعيد ألفَ مرّة.
    """
    ranked = []
    for day, period in available:
        penalty = evaluate_soft_constraints(grid, day, period, task, preferences)
        ranked.append((day, period, penalty.total))
    if rng is not None:
        rng.shuffle(ranked)
    ranked.sort(key=lambda x: x[2])
    return ranked


def _greedy_pass(grid, tasks, blocked, preferences, school=None, rng=None, allow_adjacent=False):
    """يضع ما يستطيع، ويُعيد ما تعذّر — بلا تراجعٍ ولا محاولاتٍ ضائعة.

    وكان هنا تراجعٌ أعمى: يرفع **آخرَ** ما وُضع وقد لا يكون له بالانسداد صلة،
    ثمّ يعود فيجرّب. فاستُهلكت المحاولاتُ في دورةٍ لا تُقرّب من حلّ — ورفعُ
    حدّها من خمسمئةٍ إلى ثلاثين ألفاً أعطى نتيجةً **أسوأ** على بيانات المدرسة.
    فالبحثُ الأعمى لا يُصلحه الإكثارُ منه.
    """
    leftovers = []
    for task in tasks:
        ranked = rank_slots(
            grid,
            task,
            get_available_slots(grid, task, blocked, school, allow_adjacent),
            preferences,
            rng,
        )
        if ranked:
            day, period, _ = ranked[0]
            grid.place(day, period, task)
        else:
            leftovers.append(task)
    return leftovers


def _blockers(grid, task, day, period, blocked):
    """مَن يسدّ هذه الخانةَ عن هذه المهمّة — أو `None` إن كان السدُّ لا يُرفع.

    فتفريغُ المعلّم قرارٌ إداريٌّ لا يُزاح، وتجاوزُ سقف اليوم أو التوزيع قيدٌ
    لا يُحلّ بإخراج ساكن. أمّا الشاغلُ — شعبةً أو معلّماً — فيُزاح إن وُجد له
    بديل.
    """
    slots = list(task.slots(period))
    if any(
        (m.teacher_id, day, slot) in blocked for m in task.members for slot in slots
    ):
        return None

    occupants = []
    seen = set()
    for slot in slots:
        occupant = grid.get_task_at(task.class_id, day, slot)
        if occupant is not None and id(occupant) not in seen:
            occupants.append(occupant)
            seen.add(id(occupant))
        for member in task.members:
            busy = grid.teacher_task_at(member.teacher_id, day, slot)
            if busy is not None and id(busy) not in seen:
                occupants.append(busy)
                seen.add(id(busy))
    return occupants


def _repair_pass(
    grid,
    leftovers,
    blocked,
    preferences,
    budget,
    school=None,
    allow_adjacent=False,
    allow_dense=False,
):
    """الإزاحةُ الموجَّهة: أخرِج ساكنَ الخانة، وأنزِل المتعذّرة، ثمّ أعِد الساكن.

    والفرقُ عن التراجع الأعمى أنّ الإزاحةَ تعرف **من** يسدّ الطريق بعينه: خانةٌ
    واحدةٌ ممكنةٌ لمعلّمٍ مقيَّد، شغلها زميلٌ يملك أربعاً وثلاثين غيرَها.

    والحركةُ ذرّيّة: إن تعذّر إعادةُ أحد المُزاحين رُدَّ كلُّ شيءٍ إلى مكانه.
    فلا تُبدَّل حصّةٌ متعذّرةٌ بأخرى.
    """
    #: ثلاثُ جولاتٍ بعمقِ ثلاث. والعمقُ يُقاس ولا يُخمَّن: بعمقين يبقى أربعَ
    #: عشرةَ متعذّرةً في ثانية، وبثلاثةٍ خمسٌ في ستّ ثوانٍ — وستُّ ثوانٍ ثمنٌ
    #: مقبولٌ لعمليّةٍ تُجرى مرّةً في الفصل. وبأربعةٍ يبلغ الزمنُ دقيقةً بلا
    #: مكسبٍ يُذكر.
    remaining = list(leftovers)
    for _ in range(3):
        still = []
        for task in remaining:
            if budget <= 0 or not _try_eject(
                grid, task, blocked, preferences, 3, school, allow_adjacent, allow_dense
            ):
                still.append(task)
            else:
                budget -= 1
        if len(still) == len(remaining):
            return still
        remaining = still
    return remaining


def _try_eject(
    grid, task, blocked, preferences, depth=1, school=None, allow_adjacent=False, allow_dense=False
):
    """يُخرج ساكنَ الخانةِ لينزل فيها المتعذّر — ثمّ يُعيد الساكنَ إلى بديل.

    و`depth` عمقُ السلسلة: بعمقٍ واحدٍ يجب أن يجد المُزاحُ خانةً فارغةً له،
    وبعمقين يجوز أن يُزيح هو الآخرُ ساكناً. وأبعدُ من ذلك يُقلّب الجدولَ أكثرَ
    ممّا يُصلح، وقد كفى العمقان: اثنتان بقيتا من ثمانٍ وخمسين.
    """
    for day, period in _candidate_starts(grid, task, blocked, school):
        evicted = _blockers(grid, task, day, period, blocked)
        #: إزاحةُ أكثرَ من ساكنَين تُقلّب الجدولَ أكثرَ ممّا تُصلح.
        if evicted is None or not evicted or len(evicted) > 2:
            continue

        homes = [(e, _home_of(grid, e)) for e in evicted]
        if any(home is None for _, home in homes):
            continue

        grid.begin()
        for occupant, home in homes:
            grid.remove(occupant.class_id, home[0], home[1])

        slots = list(task.slots(period))
        if all(
            is_slot_valid(grid, day, slot, task, allow_adjacent, allow_dense) for slot in slots
        ) and not any(
            grid.teacher_busy(m.teacher_id, day, slot) for m in task.members for slot in slots
        ):
            grid.place(day, period, task)
            if _rehome_all(
                grid,
                [e for e, _ in homes],
                blocked,
                preferences,
                depth,
                school,
                allow_adjacent,
                allow_dense,
            ):
                grid.commit()
                return True

        grid.rollback()
    return False


def _candidate_starts(grid, task, blocked, school):
    """مواضعُ البدء الممكنةُ للإزاحة — بصرف النظر عمّن يشغلها الآن.

    فالفرقُ عن `get_available_slots` أنّ هذه تشمل المشغولَ عمداً: الإزاحةُ
    تبحث عمّن يسدّ الطريقَ لتُخرجه. أمّا التفريغُ وكتلةُ المزدوجة وسقفُ اليوم
    فحدودٌ لا يرفعها إخراجُ ساكن.
    """
    from .scheduler_constraints import get_max_periods_for_day, joinable_pairs

    pairs = joinable_pairs(school) if task.span > 1 and school is not None else None
    for day in DAYS:
        max_p = get_max_periods_for_day(day, task.level_type)
        for period in range(1, max_p - task.span + 2):
            slots = list(task.slots(period))
            if pairs is not None and tuple(slots) not in pairs:
                continue
            if blocked and any(
                (m.teacher_id, day, slot) in blocked for m in task.members for slot in slots
            ):
                continue
            yield day, period


def _home_of(grid, task):
    for day in DAYS:
        for period in range(1, 8):
            if grid.get_task_at(task.class_id, day, period) is task:
                return (day, period)
    return None


def _rehome_all(
    grid, tasks, blocked, preferences, depth=1, school=None, allow_adjacent=False, allow_dense=False
):
    """يُعيد المُزاحين إلى خاناتٍ صحيحة، أو يُعلن الفشلَ ليتراجع المُنادي.

    والتراجعُ عند المُنادي بسجلّ الشبكة — لا هنا: فالسلسلةُ العميقةُ تُحرّك ما
    لم يضعه هذا المستوى، ولا يعرف كلُّ مستوىً إلّا ما فعله هو.
    """
    for task in tasks:
        ranked = rank_slots(
            grid,
            task,
            get_available_slots(grid, task, blocked, school, allow_adjacent, allow_dense),
            preferences,
        )
        if ranked:
            day, period, _ = ranked[0]
            grid.place(day, period, task)
            continue
        # لا خانةَ فارغةً له — فليُزِح هو الآخرُ إن بقي في العمق سعة.
        if depth > 1 and _try_eject(
            grid, task, blocked, preferences, depth - 1, school, allow_adjacent, allow_dense
        ):
            continue
        return False
    return True


def generate_schedule(
    school: School,
    academic_year: str,
    user=None,
    max_backtrack: int = 500,
) -> dict:
    """
    التوليد الرئيسي — Greedy + Backtracking

    Returns:
        dict with keys: success, grid, quality, generation, errors
    """
    start_time = time.time()
    errors = []

    # 1. بناء المهام
    tasks = build_tasks(school, academic_year)
    if not tasks:
        return {
            "success": False,
            "errors": ["لا توجد توزيعات مواد (SubjectClassAssignment). أضف التوزيعات أولاً."],
        }

    # 2. تحميل التفضيلات
    prefs_qs = TeacherPreference.objects.filter(school=school, academic_year=academic_year)
    preferences = {}
    for p in prefs_qs:
        preferences[str(p.teacher_id)] = {
            "max_daily": p.max_daily_periods,
            "max_consecutive": p.max_consecutive,
            "free_day": p.free_day,
        }

    # 2b. تحميل تفريغات المعلمين — مجموعة (teacher_id, day, period) المحظورة
    exemptions_qs = TeacherExemption.objects.filter(
        school=school,
        academic_year=academic_year,
        is_active=True,
    )
    blocked_slots: set[tuple[str, int, int | None]] = set()
    for ex in exemptions_qs:
        tid = str(ex.teacher_id)
        if ex.exemption_type == "full_day":
            # حظر كل حصص اليوم
            for p in range(1, 8):
                blocked_slots.add((tid, ex.day_of_week, p))
        else:
            blocked_slots.add((tid, ex.day_of_week, ex.period_number))

    # 3. ترتيب المهام
    sorted_tasks = sort_tasks(tasks)

    # 4. التوليد: محاولاتٌ متعدّدةٌ يُختار أفضلُها
    #
    # جدولُ هذه المدرسة إشغالُه تسعةٌ وتسعون بالمئة، وثلاثٌ وعشرون شعبةً من
    # خمسٍ وعشرين ممتلئةٌ تماماً — أي أنّ كلَّ خانةٍ فيها يجب أن تُملأ بالحصّة
    # الصحيحة. وفي مثل هذا الضيق تكون المحاولةُ الواحدةُ رهانَ حظّ: طريقٌ
    # واحدٌ إن انسدّ انسدّ.
    #
    # والمحاولاتُ تختلف بخلطِ الخانات المتساوية في العقوبة وحدَها — فالقيودُ
    # والأوزانُ لا تتغيّر، وإنّما يتغيّر أيُّ المتساويات يُجرَّب أوّلاً.
    # وكلُّ محاولةٍ تُقاس بنتيجتها **النهائيّة** — بعد استرخائها لا قبله. فقد
    # تنتهي محاولتان إلى خمسَ عشرةَ متعذّرةً ثمّ تُغلق إحداهما بالرخصة وتعجز
    # الأخرى: فاختيارُ الأفضل قبل الرخصة اختيارٌ بمقياسٍ ليس هو المطلوب.
    best = None
    for attempt in range(RESTARTS):
        rng = random.Random(attempt)
        grid = ScheduleGrid()
        leftovers = _greedy_pass(grid, sorted_tasks, blocked_slots, preferences, school, rng)
        before_repair = len(leftovers)
        leftovers = _repair_pass(
            grid, leftovers, blocked_slots, preferences, max_backtrack, school
        )
        repaired = before_repair - len(leftovers)

        # الرخصةُ الأولى: زوجٌ واحدٌ متلاصق. والقياسُ هو الذي فرض تأخيرَها —
        # السماحُ بالتلاصق من البداية يُنتج ثمانيةً وتسعين زوجاً عند خمسةٍ
        # وأربعين معلّماً، والاسترخاءُ في آخر خطوةٍ يُنتج زوجاً لكلّ متعذّرة.
        relaxed = 0
        if leftovers:
            before = len(leftovers)
            leftovers = _repair_pass(
                grid, leftovers, blocked_slots, preferences, max_backtrack, school,
                allow_adjacent=True,
            )
            relaxed = before - len(leftovers)

        # الرخصةُ الثانية — ملاذٌ أخير: يومٌ يأخذ حصّةً زائدةً عن قسمة الأسبوع،
        # أو معلّمٌ يأخذ سابعةً ثالثة.
        #
        # وحالةُ المدرسة هي التي فرضتها: المزدوجةُ الأخيرةُ في الثامن/4 خانتاها
        # الشاغرتان في يومين مختلفين، فلا زوجَ متلاصقٌ يقبلها. وكلُّ إزاحةٍ
        # جُرِّبت اصطدمت بقيدَي التوزيع والسابعة لا بقيد التلاصق: الرياضياتُ
        # خمسُ حصصٍ في خمسة أيّام، فنقلُها يجعل يوماً يومَين رياضيات، والخانةُ
        # البديلةُ الوحيدةُ سابعةٌ عند معلّمٍ بلغ حصّتَه منها.
        #
        # ونصابُ الشعبة أربعٌ وثلاثون لا يُمَسّ — فالثمنُ يُدفع من ترتيب اليوم
        # لا من المنهج، ولمعلّمٍ واحدٍ في شعبةٍ واحدة.
        densed = 0
        if leftovers:
            before = len(leftovers)
            leftovers = _repair_pass(
                grid, leftovers, blocked_slots, preferences, max_backtrack, school,
                allow_adjacent=True, allow_dense=True,
            )
            densed = before - len(leftovers)

        if best is None or len(leftovers) < len(best[1]):
            best = (grid, leftovers, repaired, relaxed, densed)
        if not best[1]:
            break

    grid, leftovers, repaired, relaxed, densed = best

    for task in leftovers:
        errors.append(f"تعذر وضع: {task.subject_name} → {task.class_name} ({task.teacher_name})")

    elapsed_ms = int((time.time() - start_time) * 1000)

    # 5. حساب الجودة
    quality = calculate_quality_score(grid, preferences, total_required=len(sorted_tasks))

    # 6. حفظ النتائج
    generation = None
    if not errors or quality["total_slots"] > 0:
        try:
            with transaction.atomic():
                # حذف الجدول القديم
                ScheduleSlot.objects.filter(
                    school=school, academic_year=academic_year, is_active=True
                ).update(is_active=False)

                # إنشاء الحصص الجديدة — تحميل أوقات الحصص (regular + thursday)
                time_config = {}
                for tc in TimeSlotConfig.objects.filter(school=school, is_break=False):
                    time_config[(tc.day_type, tc.period_number)] = (tc.start_time, tc.end_time)

                # أوقات احتياطية إذا لم يُعدَّ TimeSlotConfig
                DEFAULT_TIMES = {
                    1: (dt_time(7, 10), dt_time(7, 55)),
                    2: (dt_time(8, 0), dt_time(8, 45)),
                    3: (dt_time(8, 50), dt_time(9, 35)),
                    4: (dt_time(9, 55), dt_time(10, 40)),
                    5: (dt_time(10, 45), dt_time(11, 30)),
                    6: (dt_time(11, 35), dt_time(12, 20)),
                    7: (dt_time(12, 25), dt_time(13, 10)),
                }

                def _get_time(day: int, period: int):
                    day_type = "thursday" if day == 4 else "regular"
                    result = time_config.get((day_type, period))
                    if result:
                        return result
                    # fallback: regular config ثم default
                    result = time_config.get(("regular", period))
                    if result:
                        return result
                    return DEFAULT_TIMES.get(period, (dt_time(7, 10), dt_time(7, 55)))

                bulk = []
                for entry in grid.all_entries():
                    t = entry["task"]
                    d = entry["day"]
                    p = entry["period"]
                    # صفٌّ لكلّ (خانة × ساكن): المزدوجةُ تشغل خانتين، والشعبةُ
                    # المنقسمةُ خانةً واحدةً بحصّتين. و`elective_group` هو ما
                    # يُجيز اجتماعَ الحصّتين في القاعدة — فالقيدُ الفريدُ يشمله.
                    for slot in t.slots(p):
                        start, end = _get_time(d, slot)
                        for member in t.members:
                            bulk.append(
                                ScheduleSlot(
                                    school=school,
                                    teacher_id=member.teacher_id,
                                    class_group_id=t.class_id,
                                    subject_id=member.subject_id,
                                    day_of_week=d,
                                    period_number=slot,
                                    start_time=start,
                                    end_time=end,
                                    academic_year=academic_year,
                                    elective_group=member.subject_name if t.is_split else "",
                                    is_active=True,
                                )
                            )
                ScheduleSlot.objects.bulk_create(bulk)

                # سجل التوليد
                generation = ScheduleGeneration.objects.create(
                    school=school,
                    academic_year=academic_year,
                    generated_by=user,
                    status="draft",
                    quality_score=quality["score"],
                    hard_violations=len(errors),
                    soft_violations=quality["violations"],
                    total_slots_created=quality["total_slots"],
                    generation_time_ms=elapsed_ms,
                    config_snapshot={
                        "total_tasks": len(tasks),
                        "repaired": repaired,
                        "relaxed": relaxed,
                        "densed": densed,
                        "preferences_count": len(preferences),
                    },
                )
        except Exception as exc:
            logger.exception("فشل حفظ الجدول المولَّد: %s", exc)
            errors.append(f"فشل حفظ الجدول: {exc}")

    return {
        "success": len(errors) == 0,
        "grid": grid,
        "quality": quality,
        "generation": generation,
        "errors": errors,
        "elapsed_ms": elapsed_ms,
        "total_tasks": len(tasks),
        "repaired": repaired,
        "relaxed": relaxed,
        "densed": densed,
    }

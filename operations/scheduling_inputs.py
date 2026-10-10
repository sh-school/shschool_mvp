"""operations/scheduling_inputs.py — مدخلاتُ الجدولة المشتركة بين المحرّكات (W-20261010-004، المرحلة 1).

انتقل هنا من `scheduler.py` (المحرّك السابق) كلُّ ما يستعمله V2 والمقيِّمُ المستقلّ: المهمّةُ `Task` والعضو `Member`
وشبكةُ الجدول `ScheduleGrid` (وفيها `resource_overlapping_levels` التي يحكم بها المقيِّم)، وبناءُ المهامّ، وجرسُ المدرسة،
وتحميلُ المدخلات. **نقلٌ حرفيٌّ بلا تغيير سلوك**؛ و`scheduler.py` يعيد تصديرها فلا يتغيّر استيرادُ أحد.
"""

from __future__ import annotations

import logging
import math
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import time as dt_time

from core.models import School

from .last_period_cap import personal_last_cap
from .models import (
    ScheduleSlot,
    Subject,
    SubjectClassAssignment,
    TeacherExemption,
    TeacherPreference,
    TimeSlotConfig,
)

logger = logging.getLogger(__name__)


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
    #: سقفُ السابعة الأسبوعيّ الخاصّ بهذا المعلّم (HC8) — صفرٌ يعني «خُذ العامّ».
    last_cap: int = 0
    #: موارد هذا العضو وحده (مادّتُه) — فالمنقسمةُ لا تُدخل موادَّ أحد ساكنيها في موارد الآخر.
    resources: tuple = ()


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
    #: بنطاق مرحلة الشعبة، وحيث سرى بطل الازدواج.
    preferred_periods: list = field(default_factory=list)
    #: طبيعةُ المادّة تربويّاً — `heavy` / `activity` / `regular`، من `Subject.pedagogy`.
    #:
    #: وكانت الترجيحاتُ تشتقّها من رموزٍ محفورة (`CORE_CODES`، و`code == "PE"`)
    #: بينما المختبرُ يقيسها بهذا الحقل. فمصدرانِ لحقيقةٍ واحدة: تغيّر الإدارةُ
    #: طبيعةَ مادّةٍ من الشاشة، فيتغيّر ما يقيسه المختبرُ ولا يتغيّر ما يفعله
    #: المولّد — ثمّ يُقرأ الفرقُ خللاً في الخوارزميّة وهو خللٌ في المصدر.
    pedagogy: str = "regular"
    level_type: str = ""  # "prep" (إعدادي) أو "sec" (ثانوي) — للخميس
    #: صفُّ الشعبة («G7»…«G12») — قيدُ الخميس الصلب يخصّ الحادي عشر والثاني عشر.
    grade: str = ""
    #: سقفُ التلاصق الخاصُّ بمعلّم هذه المهمّة — صفرٌ يعني «خُذ العامّ».
    #: والخاصُّ لا يُرفع في جولة الاسترخاء: قرارٌ في حقّ معلّمٍ بعينه أثقلُ من
    #: سقفٍ عامٍّ وُضع ليُقارَب.
    consecutive_cap: int = 0
    #: أوسعُ فراغٍ يُقبل بين حصّتين لصاحب هذه المهمّة — `None` يعني «لا قيدَ
    #: شخصيّ، الفراغُ ترجيحٌ مرنٌ كما لعامّة الكادر». والصفرُ قيدٌ صحيحٌ لا
    #: غيابُ قيد: «لا فراغَ البتّة». وهو كسقف التلاصق: قرارٌ في حقّ الشخص،
    #: فلا يُرفع في جولة الاسترخاء.
    gap_cap: int | None = None
    #: نطاقُ توقيت الشعبة — فارغٌ يعني جرسَ المدرسة. به تُحوَّل (اليوم · الرقم)
    #: إلى ساعةٍ، ومعلّمُ الطابقين يُحكَم بالساعة (HC12).
    band_id: str = ""
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
        #: بالكتل لا بالحصص: `ScheduleGrid` يعدّ المهمّةَ الموضوعةَ كتلةً
        #: واحدةً مهما طالت، فقسمةُ الحصص هنا تقيس بوحدةٍ غيرِ وحدة العدّاد.
        #: صحيحٌ بالمصادفة ما دامت المزدوجةُ نصابُها أربعٌ فأقلّ، ويخطئ عند
        #: ستٍّ: ⌈6/5⌉ = كتلتان = أربعُ حصصٍ في يومٍ واحد.
        days = max(1, self.available_days)
        return max(1, math.ceil(self._blocks / days))

    @property
    def days_allowed_at_cap(self) -> int:
        """كم يوماً يجوز أن يبلغ السقف.

            daysAtCap = W mod D    (وإن قسمت بلا باقٍ فالأيّامُ كلُّها سواء)

        فستٌّ على خمسةٍ: يومٌ واحدٌ مزدوج. وستٌّ على أربعةٍ: يومان. وخمسٌ على
        خمسةٍ: لا مزدوجَ البتّة، والأيّامُ الخمسةُ كلُّها «عند السقف» وهو واحد.
        """
        days = max(1, self.available_days)
        remainder = self._blocks % days
        return remainder if remainder else days

    @property
    def _blocks(self) -> int:
        """عددُ ما تضعه الشبكةُ من هذه المهمّة — كتلةٌ لكلّ `span` حصص."""
        return math.ceil(self.weekly_periods / max(1, self.span))


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

    def __init__(
        self,
        band_times: dict | None = None,
        coverage: dict | None = None,
        break_times: dict | None = None,
        policy=None,
    ):
        #: _grid[class_id][day][period] = Task
        self._grid: dict[str, dict[int, dict[int, Task | None]]] = {}
        #: {(نطاق, نوع اليوم): {رقم الحصّة: (بداية, نهاية)}} — والمفتاح "" للافتراضيّ.
        #: فارغٌ يعني «لا أجراسَ معروفة» فيُعطَّل الحكمُ بالساعة.
        self.band_times: dict = band_times or {}
        #: {(نطاق, نوع اليوم): [(بداية, نهاية, الاسم)]} — الفسحةُ والصلاة.
        #: بها تُعرف المزدوجةُ التي تقطعها استراحةٌ (HC19)، وهي خارج
        #: `band_times` لأنّ تلك خاناتُ تدريسٍ لا فواصل.
        self.break_times: dict = break_times or {}
        #: تغطيةُ الأيّام: {معلّم: (مواضعُه، حصصُه، أيّامُه المتاحة)} — لا يومَ
        #: فارغاً لمن مواضعُه تبلغ أيّامَه إلّا بتفريغٍ من الإعدادات (HC14).
        #: والموضعُ مهمّةٌ واحدة: المزدوجةُ حصّتان في يومٍ واحد، فثلاثُ مزدوجاتٍ
        #: لا تغطّي خمسةَ أيّامٍ مهما وُزّعت — وصاحبُها مستثنىً كقليل الحصص.
        self.coverage: dict = coverage or {}
        #: رتبُ الكسر السارية — افتراضُ الشيفرة ما لم تُمرَّر سياسةُ العام.
        #: تُبنى مرّةً قبل التوليد ولا تُستعلَم في الحلقة الساخنة أبداً.
        from .constraint_registry import default_policy

        self.policy = policy or default_policy()
        #: كم مهمّةً وُضعت لكلّ معلّم — بالمواضع لا بالخانات.
        self._teacher_tasks: dict[str, int] = defaultdict(int)
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
        #: أيُّ مراحلَ تشغل المورد في التوقيت — لموردٍ لا يجمع إعداديّاً وثانويّاً.
        self._resource_levels: dict[tuple[str, int, int], Counter] = defaultdict(Counter)
        #: (مورد · يوم · حصّة) → {(نطاق, مرحلة): عدد} — النطاقُ لازمٌ لأنّ
        #: الحكمَ على المورد بالساعة لا بالرقم: جرسان مختلفان يجعلان رقمين
        #: مختلفين يتقاطعان في الملعب (HC11).
        self._resource_bands: dict[tuple[str, int, int], Counter] = defaultdict(Counter)
        #: ساكنو الشبكة بمهمّتهم — قاموسٌ لا قائمة: النسيانُ كان يعيد بناءَ
        #: القائمة كلَّها (840 عنصراً) عند كلّ إزاحةٍ، 354 ألفَ مرّةٍ في توليد.
        self._entries: dict[int, dict] = {}
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

    def touched(self) -> list[Task]:
        """المهامُّ التي تحرّكت في الإطار المفتوح — ليُحكَم فيما مسّته الحركةُ وحدَه."""
        return list({id(t): t for *_, t in (self._journal[-1] if self._journal else [])}.values())

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
            for resource_id, *_ in task.resources:
                self._resource_at[(resource_id, day, slot)] += 1
                self._resource_levels[(resource_id, day, slot)][task.level_type] += 1
                self._resource_bands[(resource_id, day, slot)][
                    (task.band_id or "", task.level_type)
                ] += 1
        # موضعُ البداية وحدَه: `check_period_variety` (HC7) يسأل عن موضع بداية الكتلة، فلو عُدّت كلُّ خانةٍ
        # تغطّيها المزدوجةُ رُفع العدّادُ على حصّتَيها وضاقت مواضعُ البدء الأربعةُ (ح1، ح2، ح4، ح6) فتعذّرت
        # كتلةٌ من نصاب 12 مزدوجة (W-20261002-014). والمفردةُ بدايتُها هي خانتُها فلا تتغيّر.
        self._subject_period[(task.subject_id, task.class_id, period)] += 1
        # كتلةٌ واحدةٌ لا حصّةٌ لكلّ خانة: `per_day_cap` يُحسب بالكتل (⌈W/D⌉ على عدد الكتل)، فلو عُدّت
        # الخاناتُ كانت المزدوجةُ تُحسب اثنتين ويضيق السقفُ إلى النصف صامتاً (W-20260930-003).
        self._subject_class_day[(task.subject_id, task.class_id, day)] += 1
        for member in task.members:
            self._teacher_tasks[member.teacher_id] += 1
        self._entries[id(task)] = {"day": day, "period": period, "task": task}

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
            for resource_id, *_ in task.resources:
                self._resource_at[(resource_id, day, slot)] -= 1
                self._resource_levels[(resource_id, day, slot)][task.level_type] -= 1
                self._resource_bands[(resource_id, day, slot)][
                    (task.band_id or "", task.level_type)
                ] -= 1
        self._subject_class_day[(task.subject_id, task.class_id, day)] -= 1
        self._subject_period[(task.subject_id, task.class_id, start)] -= 1
        for member in task.members:
            self._teacher_tasks[member.teacher_id] -= 1
        self._entries.pop(id(task), None)

    # ── الإشغال: سؤالان مختلفان ───────────────────────────────────

    def teacher_busy(self, teacher_id: str, day: int, period: int) -> bool:
        """هل هذا المعلّمُ مشغولٌ في هذا التوقيت — في أيّ شعبةٍ كانت؟"""
        return (teacher_id, day, period) in self._teacher_at

    def class_busy(self, class_id: str, day: int, period: int) -> bool:
        """هل لهذه الشعبة حصّةٌ في هذا التوقيت؟"""
        return self._class_grid(class_id)[day][period] is not None

    def teacher_task_at(self, teacher_id: str, day: int, period: int) -> Task | None:
        return self._teacher_at.get((teacher_id, day, period))

    def teacher_periods_on(self, teacher_id: str, day: int) -> list[int]:
        """خاناتُ المعلّم في يومٍ بعينه — أرقاماً."""
        return [p for d, p in self._teacher_slots.get(teacher_id, ()) if d == day]

    def interval(self, band_id: str, day: int, period: int):
        """ساعةُ (النطاق · اليوم · الرقم) — أو `None` إن لم يُعرف جرسٌ لها."""
        if not self.band_times:
            return None
        day_type = "thursday" if day == 4 else "regular"
        for key in (
            (band_id or "", day_type),
            ("", day_type),
            (band_id or "", "regular"),
            ("", "regular"),
        ):
            table = self.band_times.get(key)
            if table and period in table:
                return table[period]
        return None

    def break_between(self, band_id: str, day: int, first: int, second: int) -> str:
        """اسمُ الاستراحة الواقعةِ بين خانتين متتاليتين — أو `""` إن لم تقع.

        المزدوجةُ حصّتان متلاصقتان بالرقم، وقد تفصلهما فسحةٌ أو صلاةٌ بالساعة:
        في الطابق الأرضيّ تنتهي السادسةُ 12:20 وتبدأ السابعةُ 12:40، وبينهما
        الصلاة. والرقمُ وحدَه لا يراها.
        """
        if not self.break_times:
            return ""
        before = self.interval(band_id, day, first)
        after = self.interval(band_id, day, second)
        if not (before and after):
            return ""
        day_type = "thursday" if day == 4 else "regular"
        for key in (
            (band_id or "", day_type),
            ("", day_type),
            (band_id or "", "regular"),
            ("", "regular"),
        ):
            windows = self.break_times.get(key)
            if windows is None:
                continue
            for start, end, label in windows:
                if before[1] <= start and end <= after[0]:
                    return label or "استراحة"
            return ""
        return ""

    def resource_overlapping_levels(
        self, resource_id: str, day: int, band_id: str, period: int, tolerance: int = 0
    ) -> set[str]:
        """المراحلُ التي تشغل المورد في ساعةٍ تتقاطع مع هذه الخانة.

        الحكمُ بالساعة لا بالرقم: الجرسان مختلفان، فحصّةُ الإعداديّ الثانية
        (8:00–8:50) تلتقي حصّةَ الثانويّ الثالثة (8:45–9:35) في الملعب وإن
        اختلف رقمُهما. و`tolerance` دقائقُ الانتقال المسموحة — خمسٌ بقرار
        الإدارة 2026-09-08، فصفّان يتبادلان الملعب في خمس دقائقَ لا فوضى.
        """
        mine = self.interval(band_id, day, period)
        if mine is None:
            return set()
        mine_start = mine[0].hour * 60 + mine[0].minute
        mine_end = mine[1].hour * 60 + mine[1].minute
        found: set[str] = set()
        for slot in range(1, LAST_PERIOD + 1):
            counts = self._resource_bands.get((resource_id, day, slot))
            if not counts:
                continue
            for (other_band, level), number in counts.items():
                if number <= 0 or level in found:
                    continue
                theirs = self.interval(other_band, day, slot)
                if theirs is None:
                    continue
                start = theirs[0].hour * 60 + theirs[0].minute
                end = theirs[1].hour * 60 + theirs[1].minute
                if min(mine_end, end) - max(mine_start, start) > tolerance:
                    found.add(level)
        return found

    def same_bell(self, band_a: str, band_b: str, day: int) -> bool:
        """أنطاقان على جرسٍ واحدٍ في هذا اليوم؟

        التاسعُ 2·3·4 والثانويُّ طابقٌ واحدٌ وجرسٌ واحد من الأحد إلى الأربعاء،
        فالانتقالُ بينهما ليس انتقالاً بين طابقين. والطابقُ ليس حقلاً في
        النموذج — الجرسُ نفسُه يقوله: من اتّفق جرسُهما اتّفق طابقُهما.
        """
        if (band_a or "") == (band_b or ""):
            return True
        return all(
            self.interval(band_a, day, p) == self.interval(band_b, day, p) for p in range(1, 8)
        )

    def teacher_placed(self, teacher_id: str) -> int:
        """كم مهمّةً وُضعت للمعلّم حتّى الآن — المزدوجةُ موضعٌ واحد."""
        return self._teacher_tasks.get(teacher_id, 0)

    def teacher_empty_days(self, teacher_id: str, days) -> list[int]:
        """أيّامُ المعلّم المتاحةُ التي لا حصّةَ له فيها بعد."""
        return [d for d in days if self.teacher_periods_on_day(teacher_id, d) == 0]

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
        """كم كتلةً بدأت لهذه المادّة في هذه الحصّة من اليوم خلال الأسبوع (المزدوجةُ كتلةٌ تُعدّ عند بدايتها).

        فمادّةٌ كلُّ حصصها في الحصّة الخامسة جدولٌ لا يقبله أحد: الطالبُ يلقاها
        في التوقيت نفسه كلَّ يوم، والمعلّمُ كذلك. والتنوّعُ مقصودٌ لا مصادفة.
        """
        return self._subject_period.get((subject_id, class_id, period), 0)

    def resource_load(self, resource_id: str, day: int, period: int) -> int:
        """كم حصّةً تشغل هذا المورد في هذا التوقيت — ملعباً كان أو معملاً."""
        return self._resource_at.get((resource_id, day, period), 0)

    def resource_levels(self, resource_id: str, day: int, period: int) -> set[str]:
        """أيُّ مراحلَ (prep/sec) تشغل المورد في هذا التوقيت الآن."""
        counts = self._resource_levels.get((resource_id, day, period))
        return {level for level, n in counts.items() if n > 0} if counts else set()

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
            pairs += sum(1 for i in range(1, len(ordered)) if ordered[i] == ordered[i - 1] + 1)
        return pairs

    def teacher_periods_at(self, teacher_id: str, at: int) -> int:
        """كم حصّةً لهذا المعلّم في هذا الموضع من اليوم، طوالَ الأسبوع."""
        return sum(1 for _, period in self._teacher_slots[teacher_id] if period == at)

    def teacher_edge_periods(self, teacher_id: str) -> int:
        """طرفا اليوم معاً: الأولى والسابعة.

        وهما عبءٌ واحدٌ في ميزان المعلّم — من بدأ يومَه أوّلَ الدوام كمن أنهاه
        آخرَه (قرار الإدارة 2026-09-10). ومقياسُ «عدالة الأولى والسابعة» يعدّهما
        في سلّةٍ واحدةٍ منذ كُتب، فصار الترجيحُ يوافقه.
        """
        return self.teacher_periods_at(teacher_id, 1) + self.teacher_periods_at(
            teacher_id, LAST_PERIOD
        )

    def teacher_classes_at(self, teacher_id: str, at: int) -> set[str]:
        """شُعبُ المعلّم في هذا الموضع من اليوم — أيّامَ الأسبوع كلَّها."""
        return {
            task.class_id
            for (tid, _, period), task in self._teacher_at.items()
            if tid == teacher_id and period == at
        }

    def teacher_consecutive_counted(
        self, teacher_id: str, day: int, period: int, band_id: str | None = None
    ) -> int:
        """تتابعُ المعلّم عبر الشُّعب — وحصّةُ المكان الخاصّ تُعيد العدّاد.

        والتتابعُ صفةُ معلّمٍ لا صفةُ شعبة: حصّتان متتاليتان في شعبتين
        مختلفتين تتابعٌ يُتعب صاحبَه كما يُتعبه التتابعُ في شعبةٍ واحدة.

        وما يقطع السلسلةَ تغيُّرُ **المكان أو النشاط** — وكان يُعرَف برمزين
        محفورين (`PE`/`SCI`) يجمعان المعنيين في قائمةٍ واحدة. وكلاهما مسجَّلٌ
        في القاعدة بلا رمز:

            المكانُ    `SchedulingResource` — ملعبٌ أو معملٌ يُخرج المعلّمَ من صفّه
            النشاطُ    `Subject.pedagogy == "activity"` — بدنيّةٌ أو فنّيّةٌ أو تكنولوجيا

        فالبدنيّةُ تقطع السلسلةَ بالوجهين، والعلومُ المعمليّةُ بمعملها. ومدرسةٌ
        لم تُسجّل ملعباً تبقى بدنيّتُها قاطعةً بطبيعتها — فلا يسقط المعنى بسقوط
        أحد المصدرين.
        """
        from .scheduler_bell import cells_joined

        if band_id is None:
            here = self.teacher_task_at(teacher_id, day, period)
            band_id = getattr(here, "band_id", "") or ""
        count = 0
        for step in (-1, 1):
            p, at, at_band = period + step, period, band_id
            while 1 <= p <= 7:
                task = self.teacher_task_at(teacher_id, day, p)
                if task is None or task.resources or task.pedagogy == "activity":
                    break
                # والفسحةُ والصلاةُ تفصلان (قرارُ المالك 2026-09-24): لا يُعدّ ما عبرهما تتابعاً.
                if not cells_joined(self, day, at, at_band, p, task.band_id or ""):
                    break
                count += 1
                p, at, at_band = p + step, p, task.band_id or ""
        return count

    def teacher_widest_gap_with(self, teacher_id: str, day: int, periods) -> int:
        """أوسعُ فراغٍ في يوم المعلّم لو شغل هذه الخانات — بعدد الحصص الفارغة.

        و`would_create_gap` أدناه سؤالٌ آخر: أتنشأ فجوةٌ أم لا؟ وهو يكفي
        ترجيحاً مرناً. أمّا القيدُ الشخصيُّ فيحتاج **مقدارَ** الفراغ ليقارنه
        بسقفٍ لصاحبه، فلا يُقاس بنعم ولا.
        """
        occupied = {p for d, p in self._teacher_slots[teacher_id] if d == day}
        occupied.update(periods)
        ordered = sorted(occupied)
        if len(ordered) < 2:
            return 0
        return max(b - a - 1 for a, b in zip(ordered, ordered[1:], strict=False))

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
        return list(self._entries.values())

    def home_of(self, task: Task) -> tuple[int, int] | None:
        """(اليوم، بدايةُ الحصّة) لمهمّةٍ موضوعة — أو `None` إن لم توضع."""
        entry = self._entries.get(id(task))
        return (entry["day"], entry["period"]) if entry else None

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
    #: طبيعةُ المادّة تربويّاً — تُقرأ مرّةً كما يقرؤها المختبر، ولا تُشتقّ من رمز.
    pedagogies = dict(Subject.objects.filter(school=school).values_list("id", "pedagogy"))
    assignments = SubjectClassAssignment.objects.filter(
        school=school, academic_year=academic_year, is_active=True
    ).select_related("class_group", "subject", "teacher")

    from operations.models import SchedulingResource, TeacherExemption, TeacherPreference

    # سقوفُ التلاصق الخاصّة — حقلٌ في `TeacherPreference` كان يُحمَّل ولا
    # يُستعمَل قطّ، شأنَ `requires_double_period` قبله.
    prefs = list(TeacherPreference.objects.filter(school=school, academic_year=academic_year))
    personal_cap = {str(p.teacher_id): p.max_consecutive for p in prefs if p.max_consecutive}
    #: سقوفُ الفراغ الخاصّة — `None` لا قيد، والصفرُ قيدٌ صحيح: «لا فراغَ
    #: البتّة». فيُسأل عن العدم لا عن الصدق، وإلّا سقط الأشدُّ من القيدين.
    personal_gap = {str(p.teacher_id): p.max_gap for p in prefs if p.max_gap is not None}
    #: سقفُ السابعة الشخصيّ (HC8) — قرارٌ في حقّ معلّمٍ يفوق نصابُه سعتَه بالعدّ (W-20261003-035).
    personal_last = {
        str(p.teacher_id): personal_last_cap(p.max_last_periods)
        for p in prefs
        if personal_last_cap(p.max_last_periods)
    }

    # أيّامُ التفريغ الكاملة لكلّ معلّم — مقامُ القسمة في التوزيع.
    # ومواردُ المدرسة المحدودة: أيُّ مادّةٍ تستهلك أيَّ موردٍ وبأيّ سعة.
    resources_by_subject = defaultdict(list)
    for resource in SchedulingResource.objects.filter(
        school=school, is_active=True
    ).prefetch_related("subjects"):
        for subject in resource.subjects.all():
            resources_by_subject[str(subject.id)].append(
                (str(resource.id), resource.capacity, resource.same_level_only)
            )

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

        # الازدواجُ من القاعدة وحدَها — لا من رمزٍ محفورٍ في الشيفرة. وكان
        # يُقرأ معها `code in {"ART", "TECH"}`، فيُطفئ النائبُ الازدواجَ في
        # الشاشة ولا ينطفئ. ومصدرانِ لحقيقةٍ واحدةٍ يفترقان يوماً — وقد افترقا.
        #
        # وقرارُ الشعبة يسبق قرارَ المادّة: التكنولوجيا متباعدةٌ من السابع إلى
        # العاشر، ومزدوجةٌ في الحادي عشر/1 والثاني عشر/1 حيث هي نصفُ زوجٍ
        # متوازٍ مع الفنّيّة. وحقلُ المادّة وحده لا يسع الحالين.
        is_double = (
            a.double_period
            if a.double_period is not None
            else a.subject_id in double_period_subjects
        )
        available = len(DAYS) - len(exempt_days.get(str(a.teacher_id), ()))
        rows.append((a, level_type, is_double, max(1, available)))

    return _to_tasks(
        rows, resources_by_subject, personal_cap, personal_gap, pedagogies, personal_last
    )


def _to_tasks(
    rows,
    resources_by_subject=None,
    personal_cap=None,
    personal_gap=None,
    pedagogies=None,
    personal_last=None,
) -> list[Task]:
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
            last_cap=personal_last.get(str(a.teacher_id), 0),
            resources=tuple(resources_by_subject.get(str(a.subject_id), ())),
        )

    resources_by_subject = resources_by_subject or {}
    personal_cap = personal_cap or {}
    personal_gap = personal_gap or {}
    personal_last = personal_last or {}
    pedagogies = pedagogies or {}

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
            pedagogy=pedagogies.get(a.subject_id) or "regular",
            level_type=level_type,
            grade=a.class_group.grade or "",
            available_days=available,
            #: أضيقُ سقفٍ بين ساكني المهمّة — فالمنقسمةُ يحكمها أشدُّ معلّمَيها.
            consecutive_cap=min(
                (personal_cap[m.teacher_id] for m in members if m.teacher_id in personal_cap),
                default=0,
            ),
            #: وأضيقُ سقفِ فراغٍ كذلك — و`None` غيابُ القيد لا أوسعُه، فلا
            #: يدخل العدّ أصلاً.
            gap_cap=min(
                (personal_gap[m.teacher_id] for m in members if m.teacher_id in personal_gap),
                default=None,
            ),
            resources=tuple(used),
            parallel_group=(a.parallel_group or "").strip(),
            members=members,
            #: جرسُ الشعبة — يُقرأ من الشعبة لا يُشتقّ من مرحلتها.
            band_id=str(a.class_group.time_band_id or ""),
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
        lead, level_type, _, _ = entries[0]
        # والازدواجُ لا يُفرض على شريكٍ لا يطلبه: الفنّيّةُ مزدوجةٌ والكيمياءُ
        # ليست كذلك، وهما متوازيتان في الحادي عشر/4 والثاني عشر/4. فلو أُخذ
        # الوصفُ من أوّل العضوين لجرّت الفنّيّةُ الكيمياءَ إلى يومٍ واحد —
        # والأولى بالكيمياء يومان. فالمجموعةُ تُزدوَج إن طلب الازدواجَ
        # أعضاؤها **جميعاً**، وإلّا فحصصٌ مفردةٌ تُفرّقها القسمةُ على الأيّام.
        is_double = all(d for _, _, d, _ in entries)
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


def load_band_times(school: School) -> dict:
    """{(نطاق, نوع اليوم): {رقم: (بداية, نهاية)}} من `TimeSlotConfig` — والمفتاح "" للافتراضيّ.

    فارغٌ حين لا إعدادَ للمدرسة، فيسقط الحكمُ بالساعة (HC12) ويبقى الحكمُ بالرقم.
    """
    from collections import defaultdict as _dd

    table: dict = _dd(dict)
    for tc in TimeSlotConfig.objects.filter(school=school, is_break=False):
        table[(str(tc.band_id or ""), tc.day_type)][tc.period_number] = (tc.start_time, tc.end_time)
    return dict(table)


def load_break_times(school: School) -> dict:
    """{(نطاق, نوع اليوم): [(بداية, نهاية, الاسم)]} — الفسحةُ والصلاة.

    نظيرُ `load_band_times`، وهي تُرشّح `is_break=False` فتسقط الاستراحاتُ
    منها. وبلا استراحاتٍ معلَنةٍ يسقط حكمُ HC19 ولا تُمنع مزدوجةٌ من شيء.
    """
    from collections import defaultdict as _dd

    table: dict = _dd(list)
    for tc in TimeSlotConfig.objects.filter(school=school, is_break=True):
        table[(str(tc.band_id or ""), tc.day_type)].append(
            (tc.start_time, tc.end_time, tc.break_label or "استراحة")
        )
    return dict(table)


#: أوقاتٌ احتياطيّة حين لا `TimeSlotConfig` للمدرسة — جرسٌ واحدٌ لكلّ الأيام.
DEFAULT_TIMES = {
    1: (dt_time(7, 10), dt_time(7, 55)),
    2: (dt_time(8, 0), dt_time(8, 45)),
    3: (dt_time(8, 50), dt_time(9, 35)),
    4: (dt_time(9, 55), dt_time(10, 40)),
    5: (dt_time(10, 45), dt_time(11, 30)),
    6: (dt_time(11, 35), dt_time(12, 20)),
    7: (dt_time(12, 25), dt_time(13, 10)),
}


def bell_lookup(school: School):
    """دالّةُ (يوم، حصّة، نطاق) → (بداية، نهاية) من جرس المدرسة.

    جرسُ النطاق ليومه أوّلاً، ثمّ جرسُ المدرسة الافتراضيّ (بلا نطاق) ليومه،
    ثمّ جرسُ الأحد–الأربعاء للنطاق فالافتراضيّ، ثمّ الثابتُ الاحتياطيّ.
    والترتيبُ واحدٌ في التوليد وفي مصالحة الحصص القائمة — فلا يختلف ما
    يُكتب عمّا يُصلَح.
    """
    time_config: dict = {}
    for tc in TimeSlotConfig.objects.filter(school=school, is_break=False):
        time_config[(str(tc.band_id or ""), tc.day_type, tc.period_number)] = (
            tc.start_time,
            tc.end_time,
        )

    def lookup(day: int, period: int, band_id="") -> tuple:
        band_id = str(band_id or "")
        day_type = "thursday" if day == 4 else "regular"
        for band, kind in (
            (band_id, day_type),
            ("", day_type),
            (band_id, "regular"),
            ("", "regular"),
        ):
            result = time_config.get((band, kind, period))
            if result:
                return result
        return DEFAULT_TIMES.get(period, (dt_time(7, 10), dt_time(7, 55)))

    return lookup


def load_inputs(school: School, academic_year: str):
    """(صفوفُ التفضيل، التفضيلاتُ بالمعلّم، الخاناتُ المحجوبةُ بالتفريغ) لعامٍ دراسيّ."""
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
            for p in ScheduleSlot.PERIODS:
                blocked_slots.add((tid, ex.day_of_week, p))
        else:
            blocked_slots.add((tid, ex.day_of_week, ex.period_number))
    return prefs_qs, preferences, blocked_slots


#: الجرسُ يُقرأ مرّةً لمدّة التوليد — لا عند كلّ مرشَّحٍ لحصّةٍ مزدوجة (#109).
#: والمُزيِّنُ جزءٌ من الدالّة: حين أُدرجت `load_band_times` فوقها (#121) سرقته،

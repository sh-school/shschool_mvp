"""محوِّلُ مهامّ المولّد إلى مدخلات نموذج CP-SAT — من `build_tasks` مباشرةً لا من JSON (V2-S2، W-20261003-015).

النموذجُ المرجعيُّ (`docs/schedule_v2/cpsat_model_reference.py`) سكربتٌ مستقلٌّ يقرأ `prod_data.json`؛ فلا اعتمادَ
بينه وبين المنصّة ولا محوِّل. وهذا المحوِّلُ يبني **المدخلاتِ نفسَها** (شكلاً ومعنًى) من الحقيقة الحيّة:
المهامّ التي يبنيها `build_tasks` والخاناتُ المحجوبةُ بالتفريغ والتفضيلاتُ والجرسُ — فيقرأ المحرّكُ القادمُ ما يقرؤه
المولّدُ الحاليّ لا نسخةً منه تتقادم.

ما يفعله وما لا يفعله:
  · **لا يحلّ ولا يستورد `ortools`** — طبقةُ مدخلاتٍ صِرفةٌ قابلةٌ للاختبار بلا حلّال (S3/S4 يبنيان النموذجَ والهدف).
  · **لا يمسّ قاعدةً**: يستقبل ما حمّله المولّدُ (مهامّ، `blocked_slots`، تفضيلات، دالّةَ الجرس)، فيُختبر بلا DB.
  · **مصدرُ الحقيقة واحد:** سقفُ حصص الخميس من `get_max_periods_for_day`، والجرسُ من `bell_lookup`، والحجبُ والتفريغُ
    من `load_inputs` — لا أرقامَ منسوخةً هنا.

الشكلُ مطابقٌ للمرجع (`demand`/`bell`/`times`/`class_band`/`doubles`/`ex_full`/`ex_period`/`prefs`/`resources`)، مع حقلٍ
زائدٍ واحدٍ مقصود: `DemandRow.joint` — معرّفُ المهمّة المنقسمة (مادّتان ومعلّمان في الخانة نفسها): أعضاؤها صفوفٌ منفصلةٌ
في `demand` لكنّها **تُوضع معاً** في الخانة، وهو ما لا يعبّر عنه `elec` (بديلاتٌ يُختار منها واحد). فالمرجعُ لا يعرف
المنقسمةَ؛ والمنصّةُ تعرفها (`Task.members`).
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field

from .scheduler import LAST_PERIOD, Task
from .scheduler_constraints import get_max_periods_for_day

#: نوعا اليوم في الجرس — الخميسُ (4) له جرسٌ وحصصٌ أقلّ؛ ما سواه عاديّ.
DAY_TYPES = ("regular", "thursday")
THURSDAY = 4


def day_type_of(day: int) -> str:
    return "thursday" if day == THURSDAY else "regular"


@dataclass(frozen=True)
class DemandRow:
    """طلبٌ واحد: معلّمٌ يُدرّس مادّةً لشعبةٍ `n` حصّةً أسبوعيّاً (مجموعُ خانات مهامّها)."""

    cls: str
    subj: str
    teacher: str
    #: وسمُ المجموعة المتوازية (فارغٌ في الغالبيّة) — بديلاتٌ تتقاسم الخانةَ بلا تضارب بين أفرادها.
    elec: str
    n: int
    #: معرّفُ المهمّة المنقسمة التي يشترك فيها هذا الصفُّ مع صفوفٍ أخرى في الخانة نفسها؛ فارغٌ لغيرها.
    joint: str = ""


@dataclass(frozen=True)
class TeacherPref:
    teacher_id: str
    max_daily_periods: int | None
    max_consecutive: int | None
    max_gap: int | None
    free_day: int | None


@dataclass
class CpSatInputs:
    """كلُّ ما يقرؤه نموذجُ CP-SAT — بلا قاعدةٍ ولا JSON."""

    demand: list[DemandRow] = field(default_factory=list)
    #: مفتاحُه «نطاق|نوعُ اليوم» كالمرجع؛ القيمةُ `{"periods": [...], "touch": [(أ, ب), ...]}`.
    bell: dict[str, dict] = field(default_factory=dict)
    #: مفتاحُه «نطاق|نوعُ اليوم»؛ القيمةُ `{رقمُ الحصّة: (بدايةٌ، نهايةٌ)}` بالدقائق من منتصف الليل.
    times: dict[str, dict[int, tuple[int, int]]] = field(default_factory=dict)
    class_band: dict[str, str] = field(default_factory=dict)
    #: مرحلةُ كلّ شعبة («prep»/«sec») — لسقف حصص الخميس.
    class_level: dict[str, str] = field(default_factory=dict)
    #: صفُّ كلّ شعبة («G7»…«G12») من `ClassGroup.grade` — لـHC17 (G11/G12) وغيره.
    class_grade: dict[str, str] = field(default_factory=dict)
    #: طبيعةُ كلّ مادّة (`heavy`/`activity`/`regular`) من `Subject.pedagogy` — للقيود المرنة.
    subject_pedagogy: dict[str, str] = field(default_factory=dict)
    #: المواد التي لها حصصٌ مزدوجةٌ (مهمّةٌ بخانتين).
    doubles: frozenset[str] = frozenset()
    ex_full: frozenset[tuple[str, int]] = frozenset()
    ex_period: frozenset[tuple[str, int, int]] = frozenset()
    prefs: dict[str, TeacherPref] = field(default_factory=dict)
    #: {معرّفُ المورد: السعة}
    res_cap: dict[str, int] = field(default_factory=dict)
    #: {معرّفُ المورد: موادُّه}
    res_subjects: dict[str, frozenset[str]] = field(default_factory=dict)
    subject_names: dict[str, str] = field(default_factory=dict)
    teacher_names: dict[str, str] = field(default_factory=dict)
    class_names: dict[str, str] = field(default_factory=dict)

    @property
    def total(self) -> int:
        """مجموعُ الحصص المطلوبة — يطابق مجموعَ `span` للمهامّ."""
        return sum(row.n for row in self.demand)

    def periods(self, cls: str, day: int) -> list[int]:
        """حصصُ هذه الشعبة في هذا اليوم: جرسُ نطاقها ثمّ سقفُ المرحلة (الخميس) — كما يحكم المولّدُ الحاليّ."""
        entry = self.bell.get(f"{self.class_band.get(cls, '')}|{day_type_of(day)}")
        if not entry:
            return []
        cap = get_max_periods_for_day(day, self.class_level.get(cls, ""))
        return [p for p in entry["periods"] if p <= cap]


def _minutes(value) -> int:
    return value.hour * 60 + value.minute


def _bell(
    bands: Iterable[str], lookup: Callable[..., tuple]
) -> tuple[dict[str, dict], dict[str, dict]]:
    """الجرسُ والأوقاتُ لكلّ (نطاق، نوعُ يوم) من دالّة `bell_lookup` — وهي صاحبةُ ترتيب الاحتياط (نطاقٌ ← افتراضيّ)."""
    bell: dict[str, dict] = {}
    times: dict[str, dict[int, tuple[int, int]]] = {}
    for band in sorted(set(bands)):
        for kind in DAY_TYPES:
            day = THURSDAY if kind == "thursday" else 0
            spans = {}
            for period in range(1, LAST_PERIOD + 1):
                start, end = lookup(day, period, band)
                spans[period] = (_minutes(start), _minutes(end))
            key = f"{band}|{kind}"
            times[key] = spans
            #: التلاصقُ: الحصّتان متجاورتان زمناً (لا فسحةَ ولا صلاةَ بينهما) — وهو ما يحكم HC5 بالساعة لا بالرقم.
            bell[key] = {
                "periods": sorted(spans),
                "touch": [
                    (p, p + 1)
                    for p in sorted(spans)
                    if p + 1 in spans and spans[p + 1][0] == spans[p][1]
                ],
            }
    return bell, times


def build_inputs(
    tasks: Iterable[Task],
    blocked_slots: Iterable[tuple[str, int, int | None]] = (),
    prefs: Iterable = (),
    bell_lookup: Callable[..., tuple] | None = None,
) -> CpSatInputs:
    """مدخلاتُ النموذج من مهامّ `build_tasks` وما حمّله `load_inputs`.

    `prefs` كائناتٌ بحقول `TeacherPreference` (`prefs_qs` من `load_inputs`)، و`bell_lookup` من
    `operations.scheduler.bell_lookup(school)` — فيبقى هذا المحوِّلُ بلا قاعدة.
    """
    tasks = list(tasks)
    inputs = CpSatInputs()

    demand: dict[tuple, int] = defaultdict(int)
    doubles: set[str] = set()
    res_subjects: dict[str, set[str]] = defaultdict(set)
    for task in tasks:
        inputs.class_band[task.class_id] = task.band_id or ""
        inputs.class_names[task.class_id] = task.class_name
        if task.level_type:
            inputs.class_level[task.class_id] = task.level_type
        if task.grade:
            inputs.class_grade[task.class_id] = task.grade
        joint = ""
        if task.is_split:
            # مهمّةٌ واحدةٌ بخانةٍ واحدةٍ لساكنَيها: معرّفُها يربط صفَّيها (شعبةٌ + مادّتان + معلّمان).
            joint = "|".join(sorted(f"{m.teacher_id}:{m.subject_id}" for m in task.members))
            joint = f"{task.class_id}|{joint}"
        for member in task.members:
            demand[
                (task.class_id, member.subject_id, member.teacher_id, task.parallel_group, joint)
            ] += task.span
            inputs.subject_names[member.subject_id] = member.subject_name
            inputs.subject_pedagogy.setdefault(member.subject_id, task.pedagogy)
            inputs.teacher_names[member.teacher_id] = member.teacher_name
            if task.span > 1:
                doubles.add(member.subject_id)
            # المهمّةُ المنقسمةُ تستهلك مواردَ ساكنيها جميعاً (كما يفعل `_to_tasks`).
            for resource_id, capacity, *_ in task.resources:
                inputs.res_cap[resource_id] = capacity
                res_subjects[resource_id].add(member.subject_id)

    inputs.demand = [
        DemandRow(cls, subj, teacher, elec, n, joint)
        for (cls, subj, teacher, elec, joint), n in sorted(demand.items())
    ]
    inputs.doubles = frozenset(doubles)
    inputs.res_subjects = {rid: frozenset(subs) for rid, subs in res_subjects.items()}

    # التفريغ: يومٌ كاملٌ ← `ex_full`، وغيرُه حصّةً حصّةً ← `ex_period`. ويومٌ مفرَّغةٌ كلُّ حصصه
    # (كما يُوسِّع `load_inputs` التفريغَ الكاملَ) يُعدّ يوماً كاملاً.
    by_day: dict[tuple[str, int], set[int]] = defaultdict(set)
    for teacher_id, day, period in blocked_slots:
        if period is not None:
            by_day[(teacher_id, day)].add(period)
    full_set = set(range(1, LAST_PERIOD + 1))
    ex_full, ex_period = set(), set()
    for (teacher_id, day), periods in by_day.items():
        if periods >= full_set:
            ex_full.add((teacher_id, day))
        else:
            ex_period.update((teacher_id, day, p) for p in periods)
    inputs.ex_full, inputs.ex_period = frozenset(ex_full), frozenset(ex_period)

    for pref in prefs:
        teacher_id = str(pref.teacher_id)
        inputs.prefs[teacher_id] = TeacherPref(
            teacher_id=teacher_id,
            max_daily_periods=pref.max_daily_periods,
            max_consecutive=pref.max_consecutive,
            max_gap=pref.max_gap,
            free_day=pref.free_day,
        )

    if bell_lookup is not None:
        inputs.bell, inputs.times = _bell(set(inputs.class_band.values()), bell_lookup)
    return inputs


__all__ = ["DemandRow", "TeacherPref", "CpSatInputs", "build_inputs", "day_type_of"]

"""scheduler_audit.py — مدقّقٌ مستقلٌّ للجدول المنتهي (SCH-02).

الباني يعدّ رخصَه ولا يحفظ مواضعها: `densed=7` يقول «سبعُ حصصٍ وُضعت بكسر
القسمة» ولا يقول أيَّها. فجاء الجدولُ المعتمد في 2026-09-24 باثنتي عشرةَ مخالفةً
لـHC6 لم يرها أحدٌ حتى طُبعت ورقةُ معلّمٍ فيها حصّتا رياضيات يومَ الأحد.

فهنا يُفحص الجدولُ بعد اكتماله خانةً خانةً بالقيود نفسِها، بلا رخصة: تُرفع كلُّ
حصّةٍ من موضعها ويُسأل `slot_violations` أتقبلها الخانةُ لو وُضعت الآن. فشهادةُ
السلامة لا تأتي من عدّادٍ يحفظه الباني عن نفسه، والحكمُ هو حكمُ التوليد حرفاً
بحرف — لا نسخةٌ ثانيةٌ من القيود تفترق عنه يوماً.

والمخالفةُ تُعَدّ **بموضوعها لا بحصصها**: حصّتا الرياضيات المجتمعتان في يومٍ
مخالفةٌ واحدة (الشعبة · المادّة · اليوم) وإن رفضتها الحصّتان كلتاهما؛ ويومٌ
فارغٌ لمعلّمٍ مخالفةٌ واحدةٌ باسمه لا بعدد حصص أسبوعه.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass
from typing import TYPE_CHECKING

from .constraint_registry import REGISTRY
from .scheduler_constraints import get_max_periods_for_day, slot_violations

if TYPE_CHECKING:
    from .scheduler import ScheduleGrid, Task

#: خاناتُ التفريغ: (المعلّم، اليوم، الحصّة).
Blocked = set[tuple[str, int, int | None]]

#: أسماءُ القيود كما تُقرأ في صفحة الاعتماد — من السجلّ لا من هنا حين يوجد.
EXEMPTION = "EX"

#: قيودٌ موضوعُها المعلّمُ في أسبوعه كلّه: التغطيةُ، وسقفُ اليوم، والحدُّ الأدنى.
_TEACHER_WEEK = frozenset({"HC14", "HC16", "HC16B"})
#: قيودٌ موضوعُها المعلّمُ في يومه: التلاصقُ والفراغُ والتداخلُ بالساعة.
_TEACHER_DAY = frozenset({"HC5", "HC10", "HC12", "HC13"})
#: قيودٌ موضوعُها المادّةُ في الشعبة في يومها.
_SUBJECT_DAY = frozenset({"HC6", "HC17", "HC20"})


@dataclass(frozen=True)
class Breach:
    """مخالفةٌ واحدةٌ بموضوعها — والمفتاحُ هو ما يُعدّ."""

    code: str
    key: tuple
    class_name: str
    subject_name: str
    teacher_name: str
    day: int
    period: int

    def as_dict(self) -> dict:
        return {
            "code": self.code,
            "class": self.class_name,
            "subject": self.subject_name,
            "teacher": self.teacher_name,
            "day": self.day,
            "period": self.period,
        }


def _key(code: str, task: Task, day: int, period: int) -> tuple:
    #: الحصّةُ المقسومةُ لها معلّمان: المخالفةُ لهما معاً لا لأوّلهما — فلا تُعدّ مرّتين باسمَين.
    teachers = tuple(sorted(m.teacher_id for m in task.members))
    if code in _TEACHER_WEEK:
        return (code, teachers)
    if code in _TEACHER_DAY:
        return (code, teachers, day)
    if code in _SUBJECT_DAY:
        return (code, task.class_id, task.subject_id, day)
    return (code, task.class_id, day, period)


def task_breaches(grid: ScheduleGrid, task: Task, blocked: Blocked | None = None) -> list[Breach]:
    """مخالفاتُ حصّةٍ موضوعةٍ في موضعها — تُرفع وتُسأل ثمّ تُعاد كما كانت."""
    home = grid.home_of(task)
    if home is None:
        return []
    day, period = home
    # إطارُ التراجع بلا أنواعٍ بعد في `ScheduleGrid` (SCH-16) — كما في `scheduler_settle`.
    grid.begin()  # type: ignore[no-untyped-call]
    try:
        grid.remove(task.class_id, day, period)
        codes = slot_violations(grid, day, period, task)
    finally:
        grid.rollback()  # type: ignore[no-untyped-call]
    if blocked and any(
        (m.teacher_id, day, slot) in blocked for m in task.members for slot in task.slots(period)
    ):
        codes.append(EXEMPTION)
    return [
        Breach(
            code=code,
            key=_key(code, task, day, period),
            class_name=task.class_name,
            subject_name=task.subject_name,
            teacher_name=task.teacher_name,
            day=day,
            period=period,
        )
        for code in codes
    ]


def grid_breaches(
    grid: ScheduleGrid, tasks: Iterable[Task], blocked: Blocked | None = None
) -> list[Breach]:
    """مخالفاتُ الجدول كلِّه — واحدةٌ لكلّ موضوع، بترتيبٍ ثابت."""
    found: dict[tuple, Breach] = {}
    for task in tasks:
        for breach in task_breaches(grid, task, blocked):
            found.setdefault(breach.key, breach)
    return sorted(found.values(), key=lambda b: (b.code, b.class_name, b.day, b.period))


def breach_keys(
    grid: ScheduleGrid, tasks: Iterable[Task], blocked: Blocked | None = None
) -> set[tuple]:
    """مفاتيحُ المخالفات وحدَها — للمقارنة قبل الحركة وبعدها."""
    return {b.key for task in tasks for b in task_breaches(grid, task, blocked)}


def summary(breaches: list[Breach]) -> dict:
    """ما يُحفظ في لقطة التوليد: العددُ بكلّ رمز، والقائمةُ بأسمائها."""
    by_code: dict[str, int] = {}
    for b in breaches:
        by_code[b.code] = by_code.get(b.code, 0) + 1
    return {"count": len(breaches), "by_code": by_code, "items": [b.as_dict() for b in breaches]}


def blockers(
    grid: ScheduleGrid, task: Task, blocked: Blocked | None = None, limit: int = 3
) -> list[tuple[str, int]]:
    """القيودُ التي تمنع أكثرَ خاناتِ مهمّةٍ لم تجد موضعاً — (رمزٌ، عددُ الخانات) (SCH-15).

    «تعذّر وضع» تقول إنّ الحصّةَ بلا موضعٍ ولا تقول **لماذا**، فيبقى النائبُ يخمّن: أالمعلّمُ
    مشغول؟ أم الشعبةُ ممتلئة؟ أم قسمةُ المادّة؟ فتُسأل كلُّ خانةٍ في الأسبوع أيَّ قيدٍ صلبٍ
    يرفضها (`slot_violations` بلا رخصة)، وتُعدّ الرموزُ — فأكثرُها منعاً هو الجواب.
    """
    counts: Counter[str] = Counter()
    for day in range(5):
        last = get_max_periods_for_day(day, getattr(task, "level_type", ""))
        for period in range(1, last - task.span + 2):
            codes = set(slot_violations(grid, day, period, task))
            if blocked and any(
                (m.teacher_id, day, slot) in blocked
                for m in task.members
                for slot in task.slots(period)
            ):
                codes.add(EXEMPTION)
            counts.update(codes)
    # وعند التعادل بترتيب الرمز — ليثبت الجوابُ بين تشغيلٍ وآخر.
    return sorted(counts.items(), key=lambda item: (-item[1], item[0]))[:limit]


def unplaced_message(grid: ScheduleGrid, task: Task, blocked: Blocked | None = None) -> str:
    """سطرُ «تعذّر وضع» مع أكثر ما منعها — بأسماء القيود لا برموزها."""
    head = f"تعذر وضع: {task.subject_name} → {task.class_name} ({task.teacher_name})"
    why = "؛ ".join(
        f"{'تفريغُ معلّم' if code == EXEMPTION else REGISTRY[code].title if code in REGISTRY else code}"
        f" ({count} خانة)"
        for code, count in blockers(grid, task, blocked)
    )
    return f"{head} — أكثرُ ما منعها: {why}" if why else head

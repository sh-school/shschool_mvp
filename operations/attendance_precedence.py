"""أسبقيّةُ حالة الطالب في الحصّة — المصدرُ الوحيد للترتيب (W-20261004-025، D-420م).

كان الحسمُ موزَّعاً على طبقاتٍ لا تعرف بعضها: الكتابةُ تمنع المعلّمَ فوق صفّ المشرف، والعرضُ يقدّم تثبيتَ المشرف على الإدخال،
والخروجُ يقلب الحاضرَ غائباً. فاجتمعت ثلاثةُ ترتيباتٍ في الشيفرة. وهنا ترتيبٌ واحد، وكلُّ طبقةٍ تسأله:

1. **قرارُ تصحيح** — إدخالٌ صحّح رصداً سابقاً بسببٍ.
2. **إدخالُ المعلّم** — نهائيٌّ بلا اعتماد (أمر المالك 2026-10-09)، ويغلب رصدَ المشرف السابق في الحصّة نفسِها (D-420م، الخيارُ أ).
3. **رصدُ المشرف** — يملأ الفراغَ فقط.
4. **الخروجُ** — عرضٌ لا يغيّر حالة (قرار 2026-10-04: غائبٌ وخروجٌ لا يجتمعان).

والدالّةُ خالصة: لا قاعدةَ ولا ساعة. والتربيةُ الخاصّة (D-129م) لا تغيّر الترتيب؛ تغيّر أساسَ القرار في `attendance_entries`.
"""

from __future__ import annotations

from dataclasses import dataclass

#: الرتبُ من الأعلى إلى الأدنى — الجدولُ الوحيد؛ لا يقارن أحدٌ رتبةً بغيره.
CORRECTION = "correction"
TEACHER_ENTRY = "teacher_entry"
SUPERVISOR = "supervisor"
RANK_ORDER = (CORRECTION, TEACHER_ENTRY, SUPERVISOR)

#: مصدرُ الصفّ في `StudentAttendance` ← رتبتُه. وما ليس هنا (عيادة، بوّابة…) رصدٌ بشريٌّ آخر لا يُكتب فوقه.
SOURCE_RANK = {
    "teacher": TEACHER_ENTRY,
    "teacher_late": TEACHER_ENTRY,
    "supervisor": SUPERVISOR,
}

#: مصادرُ يجوز لإدخالِ المعلّم أن يحلّ محلَّها: رتبتُها لا تعلو رتبتَه.
OVERWRITABLE_SOURCES = frozenset(
    source
    for source, rank in SOURCE_RANK.items()
    if RANK_ORDER.index(rank) >= RANK_ORDER.index(TEACHER_ENTRY)
)

NO_SOURCE = ""


@dataclass(frozen=True)
class Mark:
    """حالةٌ قالها مصدرٌ واحد."""

    status: str
    late_minutes: int | None = None
    whereabouts: str = ""


@dataclass(frozen=True)
class Resolution:
    """ما يُعرض ويُحتسب: الحالةُ الغالبة ومصدرُها. و`away` عرضٌ وحده — لا يقلب `status`."""

    status: str
    late_minutes: int | None
    whereabouts: str
    source: str
    away: bool = False

    @property
    def is_empty(self) -> bool:
        return self.source == NO_SOURCE


EMPTY = Resolution("", None, "", NO_SOURCE)


def resolve_attendance(
    *,
    correction: Mark | None = None,
    teacher_entry: Mark | None = None,
    supervisor: Mark | None = None,
    left_and_not_returned: bool = False,
) -> Resolution:
    """الحالةُ الغالبةُ لطالبٍ في حصّةٍ من مدخلاتها — الأعلى رتبةً يغلب، والخروجُ يُوسَم ولا يقلب."""
    by_rank = {CORRECTION: correction, TEACHER_ENTRY: teacher_entry, SUPERVISOR: supervisor}
    for rank in RANK_ORDER:
        mark = by_rank[rank]
        if mark is not None:
            return Resolution(
                mark.status,
                mark.late_minutes,
                mark.whereabouts,
                rank,
                away=left_and_not_returned,
            )
    return Resolution("", None, "", NO_SOURCE, away=left_and_not_returned)


def may_overwrite(existing_source: str) -> bool:
    """أيجوز لإدخال المعلّم أن يكتب فوق صفٍّ مصدرُه هذا؟ — مشرفٌ أو معلّمٌ نعم، وعيادةٌ أو بوّابةٌ أو نظامٌ لا."""
    return existing_source in OVERWRITABLE_SOURCES

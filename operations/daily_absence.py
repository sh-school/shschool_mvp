"""تقريرُ غياب اليوم — طالبٌ في سطر، لأيّ تاريخ، على بيانات الرصد كلِّها.

يحلّ محلَّ «سجلّات الحضور والغياب» القديمة (قرارُ 2026-09-13)، التي كانت تعدّ
**السجلّات** لا الطلاب: الغائبُ سبعَ حصصٍ يظهر سبعَ مرّات. وهنا لكلّ طالبٍ سطرٌ
بحصص غيابه وتأخّره وحالِه في كلّ حصّةٍ من حصص يومه.

**وسمُ الوزارة:** الغائبُ في الحصّتين الأولى والثانية يُرفع في نظام الوزارة
«غائباً» — بعذرٍ أو بدونه بحسب حاله. والرفعُ يفعله مشرفُ الجناح في نظام
الوزارة خارجَ منصّتنا (قرارُ 2026-09-13)، فالمنصّةُ تُعدّ له القائمةَ فقط.

ويشمل كلَّ الشُّعب: ما في الأجنحة (رصدُ المشرف) وما خارجَها كالتربية الخاصّة
(رصدُ المعلّم) — فالمصدرُ `StudentAttendance` أيّاً كان من كتبه. والمنسّقُ
يرى قسمَه: معلّمي قسمه وحصصَهم، كما كان.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field

from django.db.models import Q

from core.models.academic import grade_order
from operations.models import Session, StudentAttendance

#: حصّتا الرفع الوزاريّ: الأولى والثانية بترتيب خانات يوم الشعبة.
MINISTRY_PERIODS = 2

#: حرفُ الحال في الخانة.
LETTER = {"present": "ح", "absent": "غ", "late": "م", "excused": "ع"}


@dataclass(frozen=True)
class Slot:
    """خانةٌ من حصص الشعبة في اليوم."""

    number: int
    start: dt.time
    status: str  # present · absent · late · excused · "" (لم تُرصد)
    excused: bool = False

    @property
    def letter(self) -> str:
        if self.status == "absent" and self.excused:
            return LETTER["excused"]
        return LETTER.get(self.status, "·")


@dataclass(frozen=True)
class StudentDay:
    student: object
    class_group: object
    slots: tuple[Slot, ...]
    #: خاناتٌ فارغةٌ تُكمل عرضَ الجدول حين يومُ الشعبة أقصر (الخميسُ ستٌّ لا سبع).
    padding: range = range(0)

    @property
    def absent_periods(self) -> int:
        return sum(1 for s in self.slots if s.status == "absent")

    @property
    def late_periods(self) -> int:
        return sum(1 for s in self.slots if s.status == "late")

    @property
    def unrecorded_periods(self) -> int:
        return sum(1 for s in self.slots if not s.status)

    @property
    def ministry_flag(self) -> str:
        """«غاب الأولى والثانية» لنظام الوزارة — بعذرٍ أو بدونه — أو فارغ.

        الحصّتان الأوليان بترتيب خانات الشعبة. وإن كانت إحداهما لم تُرصد فلا
        حكم: لا يُرفع طالبٌ على رصدٍ ناقص.
        """
        first = [s for s in self.slots if s.number <= MINISTRY_PERIODS]
        if len(first) < MINISTRY_PERIODS or any(not s.status for s in first):
            return ""
        if all(s.status == "absent" for s in first):
            return "excused" if all(s.excused for s in first) else "unexcused"
        return ""

    @property
    def ministry_label(self) -> str:
        return {"excused": "غائب بعذر", "unexcused": "غائب بلا عذر"}.get(self.ministry_flag, "")


@dataclass
class DailyReport:
    day: dt.date
    rows: list[StudentDay]
    max_periods: int
    #: عددُ الطلاب المرصودين في اليوم كلِّه (لا السجلّات).
    students_recorded: int = 0
    scoped_to_department: bool = False
    notes: list[str] = field(default_factory=list)

    @property
    def absent_students(self) -> int:
        return sum(1 for r in self.rows if r.absent_periods)

    @property
    def late_students(self) -> int:
        return sum(1 for r in self.rows if r.late_periods)

    @property
    def ministry_rows(self) -> list[StudentDay]:
        return [r for r in self.rows if r.ministry_flag]

    @property
    def numbers(self) -> list[int]:
        return list(range(1, self.max_periods + 1))


def daily_report(school, day: dt.date, *, teacher_ids=None) -> DailyReport:
    """طلابُ اليوم الذين غابوا أو تأخّروا حصّةً فأكثر — كلٌّ في سطر.

    `teacher_ids`: نطاقُ المنسّق (معلّمو قسمه) — `None` للمدرسة كلِّها.
    """
    sessions = (
        Session.objects.filter(school=school, date=day)
        .exclude(status="cancelled")
        .select_related("class_group")
        .order_by("class_group_id", "start_time")
    )
    if teacher_ids is not None:
        sessions = sessions.filter(teacher_id__in=teacher_ids)

    # خاناتُ كلّ شعبة بترتيب الساعة — زوجُ الاختيار خانةٌ واحدة.
    slots_of: dict = {}
    for session in sessions:
        starts = slots_of.setdefault(session.class_group_id, {})
        starts.setdefault(session.start_time, session.class_group)
    numbered = {
        cg_id: {start: n for n, start in enumerate(sorted(starts), start=1)}
        for cg_id, starts in slots_of.items()
    }

    attendance = (
        StudentAttendance.objects.filter(school=school, session__date=day)
        .filter(Q(session__class_group_id__in=list(slots_of)))
        .select_related("student", "session__class_group")
        .order_by(grade_order("session__class_group__grade"), "student__full_name")
    )
    if teacher_ids is not None:
        attendance = attendance.filter(session__teacher_id__in=teacher_ids)

    marks: dict = {}
    for row in attendance:
        cg_id = row.session.class_group_id
        student_marks = marks.setdefault(
            row.student_id,
            {"student": row.student, "class_group": row.session.class_group, "by": {}},
        )
        start = row.session.start_time
        # خانةٌ حضرها في إحدى حصّتَي الزوج حاضرةٌ ولو كُتب في الأخرى غير ذلك.
        current = student_marks["by"].get(start)
        if (
            current is None
            or current[0] not in ("present", "late")
            or row.status in ("present", "late")
        ):
            student_marks["by"][start] = (row.status, bool(row.excuse_type))
        student_marks["cg_id"] = cg_id

    rows = []
    for data in marks.values():
        cg_id = data["cg_id"]
        order = numbered.get(cg_id, {})
        slots = tuple(
            Slot(n, start, *data["by"].get(start, ("", False)))
            for start, n in sorted(order.items(), key=lambda item: item[1])
        )
        if not any(s.status in ("absent", "late") for s in slots):
            continue
        rows.append(StudentDay(data["student"], data["class_group"], slots))

    width = max((len(o) for o in numbered.values()), default=0)
    rows = [
        StudentDay(r.student, r.class_group, r.slots, range(width - len(r.slots))) for r in rows
    ]
    rows.sort(key=lambda r: (r.class_group.school_order, r.student.full_name))
    return DailyReport(
        day=day,
        rows=rows,
        max_periods=width,
        students_recorded=len(marks),
        scoped_to_department=teacher_ids is not None,
    )

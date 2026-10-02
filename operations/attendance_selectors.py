"""قراءاتُ شاشات رصد المعلّم واعتمادِه — طبقةُ قراءةٍ لا تكتب (W-20261002-020).

الكتابةُ في `attendance_entries` والقرارُ في `attendance_policy`؛ وهذه الوحدةُ تجمع ما تعرضه الشاشاتُ فقط: سطرُ كلّ طالبٍ
للمعلّم، وطابورُ الاعتماد لحاملِ الجناح (أو للقيادة حين لا حاملَ)، وتقريرُ «غيرُ معتمَد بعد X ساعة». وتُبقي الواجهاتِ
رقيقةً (سقّاطةُ الطبقات: لا ORM في الـview).

**المعلَّقُ ليس حضوراً ولا غياباً:** حالةُ الطالب الفعليّةُ تُقرأ من `StudentAttendance` (المعتمَد) وحدَه، والمبدئيُّ يُعرض
وسماً «بانتظار الاعتماد» بجانبها لا بدلها — فلا يُعدّ في ملخّص الحصّة ولا في عدّاد الغياب قبل القرار.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from django.utils import timezone

from core.models import StudentEnrollment

from .attendance_entries import EVIDENCE_TYPES, PendingRow, unapproved_report
from .attendance_policy import approval_holder, can_approve, can_enter, holder_gap
from .models import AttendanceEntry, StudentAttendance

if TYPE_CHECKING:
    from core.models import CustomUser, School

    from .models import Session

#: نافذةُ الطابور بالأيّام: إدخالٌ أقدمُ منها يخرج من طابور الاعتماد ويبقى في تقرير «غيرُ معتمَد».
QUEUE_DAYS = 14

#: نافذةُ عرض «تصحيحٌ دون معاينة» للنائب بالأيّام.
CORRECTIONS_DAYS = 30


@dataclass(frozen=True)
class StudentLine:
    """سطرُ طالبٍ في شاشة المعلّم: المعتمَدُ، وما أدخله المعلّمُ ومصيرُه."""

    student: CustomUser
    effective_status: str | None
    effective_source: str | None
    effective_minutes: int | None
    correction: dict[str, Any] | None
    entry: AttendanceEntry | None
    entry_state: str
    decision_reason: str

    @property
    def awaiting(self) -> bool:
        return self.entry_state == "pending"


def _head_entries(session: Session) -> dict[object, AttendanceEntry]:
    heads = AttendanceEntry.objects.filter(
        session=session, superseded_by__isnull=True
    ).select_related("decision")
    return {entry.student_id: entry for entry in heads}


def _state(entry: AttendanceEntry | None) -> tuple[str, str]:
    if entry is None:
        return "none", ""
    decision = getattr(entry, "decision", None)
    if decision is None:
        return "pending", ""
    return str(decision.decision), str(decision.reason)


def student_lines(session: Session) -> list[StudentLine]:
    """سطرُ كلّ طالبٍ مقيَّدٍ في شعبة الحصّة — للمعلّم الفعليّ وللاطّلاع بعد النافذة (V1–V3)."""
    enrollments = (
        StudentEnrollment.objects.filter(class_group=session.class_group, is_active=True)
        .select_related("student")
        .order_by("student__full_name")
    )
    effective = {row.student_id: row for row in StudentAttendance.objects.filter(session=session)}
    heads = _head_entries(session)
    lines = []
    for enrollment in enrollments:
        student = enrollment.student
        row = effective.get(student.id)
        entry = heads.get(student.id)
        state, reason = _state(entry)
        lines.append(
            StudentLine(
                student=student,
                effective_status=row.status if row else None,
                effective_source=row.source if row else None,
                effective_minutes=row.late_minutes if row else None,
                correction=row.unobserved_correction if row else None,
                entry=entry,
                entry_state=state,
                decision_reason=reason,
            )
        )
    return lines


def student_line(session: Session, student: CustomUser) -> StudentLine:
    """سطرُ طالبٍ واحدٍ بعد إدخالٍ — يُعاد رسمُه وحدَه (HTMX)."""
    row = StudentAttendance.objects.filter(session=session, student=student).first()
    entry = (
        AttendanceEntry.objects.filter(session=session, student=student, superseded_by__isnull=True)
        .select_related("decision")
        .first()
    )
    state, reason = _state(entry)
    return StudentLine(
        student=student,
        effective_status=row.status if row else None,
        effective_source=row.source if row else None,
        effective_minutes=row.late_minutes if row else None,
        correction=row.unobserved_correction if row else None,
        entry=entry,
        entry_state=state,
        decision_reason=reason,
    )


def teacher_may_enter_now(user: CustomUser, session: Session, lines: list[StudentLine]) -> bool:
    """أيُدخل هذا المستخدمُ الآن؟ — فحصٌ واحدٌ بأوّل طالبٍ (الكلُّ مقيَّدٌ في الشعبة)، لا استعلاماتٌ بعدد الطلاب."""
    if not lines:
        return False
    return bool(can_enter(user, session, lines[0].student))


def teacher_page_context(user: CustomUser, session: Session) -> dict[str, Any]:
    """سياقُ شاشة المعلّم في حصّةٍ لا يرصد فيها مباشرةً (شُعب الأجنحة): المعتمَدُ والمبدئيُّ والنقراتُ والخروج.

    النافذةُ تُحسب هنا لا في القالب: داخلَها إدخالٌ وتصحيح، وبعدها قراءةٌ فقط تُبقي ما أُدخل وحالتَه ظاهراً (V1).
    """
    from .class_exit import exits_of_session
    from .services import AttendanceService

    lines = student_lines(session)
    exits = exits_of_session(session)
    is_teacher = user.id == session.teacher_id
    rows = []
    for line in lines:
        rows.append(
            {
                "student": line.student,
                "line": line,
                "status": line.effective_status or "unmarked",
                "tap_minutes": (
                    line.effective_minutes if line.effective_source == "teacher_late" else None
                ),
                "exit": exits.get(line.student.id, (None, []))[0],
                "exit_count": len(exits.get(line.student.id, (None, []))[1]),
            }
        )
    return {
        "session": session,
        "can_tap_late": is_teacher,
        "can_enter": is_teacher and teacher_may_enter_now(user, session, lines),
        "exits": exits,
        "out_now": sum(1 for cur, _ in exits.values() if cur is not None),
        "students_data": rows,
        "summary": AttendanceService.get_session_summary(session),
        "recorded": any(line.effective_source == "supervisor" for line in lines),
        "pending_count": sum(1 for line in lines if line.awaiting),
    }


@dataclass(frozen=True)
class QueueItem:
    """إدخالٌ معلَّقٌ ينتظر قرارَ هذا المستخدم."""

    entry: AttendanceEntry
    age_hours: float
    as_leadership: bool
    gap: str | None


def approval_queue(
    user: CustomUser, school: School, *, now: dt.datetime | None = None, days: int = QUEUE_DAYS
) -> list[QueueItem]:
    """الإدخالاتُ المعلَّقةُ التي يملك هذا المستخدمُ قرارَها: حاملُ جناحها يومَ حصّتها، أو القيادةُ حين لا حاملَ فعليّاً."""
    moment = now or timezone.now()
    since = timezone.localtime(moment).date() - dt.timedelta(days=days)
    pending = (
        AttendanceEntry.objects.filter(
            school=school,
            superseded_by__isnull=True,
            decision__isnull=True,
            session__date__gte=since,
        )
        .select_related("session__class_group__wing", "student", "entered_by")
        .order_by("entered_at")
    )
    verdicts: dict[tuple[object, object], bool] = {}
    items = []
    for entry in pending:
        key = (entry.session_id, entry.entered_by_id)
        if key not in verdicts:
            verdicts[key] = bool(can_approve(user, entry.session, entered_by=entry.entered_by))
        if not verdicts[key]:
            continue
        gap = holder_gap(entry.session)
        items.append(
            QueueItem(
                entry=entry,
                age_hours=(moment - entry.entered_at).total_seconds() / 3600,
                as_leadership=approval_holder(entry.session) is None,
                gap=gap,
            )
        )
    return items


@dataclass(frozen=True)
class CorrectionItem:
    """تصحيحٌ دون معاينة لقراءة النائب: من صحّح ولأيّ سبب وبأيّ دليل — السببُ الحرُّ لأهل الاعتماد وحدَهم."""

    row: StudentAttendance
    tag: dict[str, Any]

    @property
    def evidence_label(self) -> str:
        return EVIDENCE_TYPES.get(str(self.tag.get("type")), "—")


def recent_corrections(
    school: School, *, now: dt.datetime | None = None, days: int = CORRECTIONS_DAYS
) -> list[CorrectionItem]:
    """تصحيحاتُ المشرف الموسومةُ لحصصِ آخر `days` يوماً، الأحدثُ أوّلاً — قراءةٌ لمدرسةٍ واحدة."""
    moment = now or timezone.now()
    since = timezone.localtime(moment).date() - dt.timedelta(days=days)
    rows = (
        StudentAttendance.objects.filter(
            school=school, unobserved_correction__isnull=False, session__date__gte=since
        )
        .select_related("session__class_group", "student", "marked_by")
        .order_by("-updated_at")
    )
    return [CorrectionItem(row=row, tag=row.unobserved_correction or {}) for row in rows]


@dataclass(frozen=True)
class UnapprovedSession:
    """سطرُ التقرير: حصّةٌ فيها إدخالاتٌ معلَّقةٌ مضى عليها الحدّ — بالعدد لا بأسماء الطلاب ولا حالاتهم."""

    session: Session
    count: int
    oldest_hours: float
    holder_gap: str | None


def unapproved_by_session(
    school: School, *, hours: float, now: dt.datetime | None = None
) -> list[UnapprovedSession]:
    """تقريرُ «غيرُ معتمَد بعد X ساعة» مجمَّعاً بالحصّة: من يتصرّف فيه (الحاملُ أو القيادةُ حين لا حاملَ فعليّاً) لا المعلّمُ وحدَه."""
    grouped: dict[object, list[PendingRow]] = {}
    for row in unapproved_report(school, older_than_hours=hours, now=now):
        grouped.setdefault(row.entry.session_id, []).append(row)
    result = [
        UnapprovedSession(
            session=rows[0].entry.session,
            count=len(rows),
            oldest_hours=max(r.age_hours for r in rows),
            holder_gap=rows[0].holder_gap,
        )
        for rows in grouped.values()
    ]
    return sorted(result, key=lambda item: -item.oldest_hours)

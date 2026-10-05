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
from uuid import UUID

from django.db.models import Count, Q
from django.utils import timezone

from core.models import StudentEnrollment

from .attendance_entries import EVIDENCE_TYPES, PendingRow, unapproved_report
from .attendance_policy import approval_holder, can_approve, can_enter, holder_gap
from .models import AttendanceEntry, Session, StudentAttendance

if TYPE_CHECKING:
    from core.models import CustomUser, School


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


#: سببُ إغلاق الإدخال بنصٍّ للمعلّم — يُعرض سطراً واحداً في رأس الحصّة حين لا أزرارَ (وإلّا بدت البطاقاتُ فارغةً بلا تفسير).
ENTRY_CLOSED = {
    "not_teacher": "لست معلّمَ هذه الحصّة — للاطّلاع فقط",
    "before_start": "لم تبدأ الحصّةُ بعد",
    "after_window": "انتهت نافذةُ الإدخال (آخرُ اليوم الدراسيّ)",
    "developer": "حسابُ المطوّر لا يُدخل",
    "cancelled": "الحصّةُ ملغاة",
}


def entry_closed_reason(user: CustomUser, session: Session, lines: list[StudentLine]) -> str:
    """سطرُ سبب إغلاق الإدخال لهذا المستخدم، أو «» إن كان مفتوحاً."""
    if not lines:
        return ""
    verdict = can_enter(user, session, lines[0].student)
    return "" if verdict else ENTRY_CLOSED.get(verdict.reason, "الإدخالُ مغلقٌ لهذه الحصّة")


@dataclass(frozen=True)
class GridCell:
    """خليّةُ طالبٍ في حصّةٍ بشبكة المعلّم: ما يُعرض رمزاً صغيراً — المبدئيُّ المعلَّق بوسمٍ، وإلّا المعتمَدُ الفعليّ."""

    shown: str  # present | absent | late | excused | "" (لم يُرصد)
    pending: bool


@dataclass(frozen=True)
class GridColumn:
    session: Session
    number: int
    is_focus: bool


def teacher_grid(
    session: Session, student_ids: list[UUID]
) -> tuple[list[GridColumn], dict[UUID, dict[UUID, GridCell]]]:
    """أعمدةُ شبكة المعلّم وخلاياها: حصصُ هذا المعلّم اليومَ في الشعبة نفسِها (كشفُ المشرف بالمكوّن نفسِه مقتصراً على حصصه).

    الحصّةُ المفتوحةُ عمودُ الإدخال، وبقيّةُ حصصه رموزٌ للاطّلاع. والقراءةُ بثلاثة استعلاماتٍ لكلّ الشبكة لا لكلّ خليّة.
    """
    sessions = list(
        Session.objects.filter(
            class_group_id=session.class_group_id, date=session.date, teacher_id=session.teacher_id
        )
        .exclude(status="cancelled")
        .order_by("start_time")
    )
    ids = [s.id for s in sessions]
    effective = {
        (r.student_id, r.session_id): r.status
        for r in StudentAttendance.objects.filter(session_id__in=ids)
    }
    pending = {
        (e.student_id, e.session_id): e.status
        for e in AttendanceEntry.objects.filter(
            session_id__in=ids, superseded_by__isnull=True, decision__isnull=True
        )
    }
    cells: dict[UUID, dict[UUID, GridCell]] = {}
    for student_id in student_ids:
        row: dict[UUID, GridCell] = {}
        for s in sessions:
            key = (student_id, s.id)
            waiting = key in pending
            row[s.id] = GridCell(
                shown=str(pending.get(key) or effective.get(key) or ""), pending=waiting
            )
        cells[student_id] = row
    columns = [GridColumn(s, i + 1, s.id == session.id) for i, s in enumerate(sessions)]
    return columns, cells


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
    columns, cells = teacher_grid(session, [line.student.id for line in lines])
    return {
        "grid_cols": columns,
        "grid_cells": cells,
        "session": session,
        # النقرتان لا تُعرضان إلا حيث تُقبلان: «دخل الآن» بنافذة الحصّة نفسِها و«خرج بإذن» بنافذة اليوم (وإلّا ردّ الخادمُ 403 فتتراكم التنبيهات).
        "can_tap_late": bool(
            is_teacher
            and lines
            and AttendanceService.may_tap("late", user, session, lines[0].student)
        ),
        "can_tap_out": bool(
            is_teacher
            and lines
            and AttendanceService.may_tap("out", user, session, lines[0].student)
        ),
        "can_enter": is_teacher and teacher_may_enter_now(user, session, lines),
        "entry_closed": entry_closed_reason(user, session, lines),
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


def session_entry_states(session_ids: list[Any]) -> dict[Any, str]:
    """حالةُ رصد كلّ حصّةٍ في استعلامٍ واحد (شارةُ لوحة المعلّم، W-20261003-038): `none` لم يُدخَل، `pending` بانتظار
    الاعتماد، `approved` معتمَد.

    تُقرأ من رؤوس الإدخالات (`superseded_by` فارغ) لا من `StudentAttendance`: المعلَّقُ ليس حضوراً ولا غياباً فيُعرض وسماً.
    أيُّ إدخالٍ بلا قرارٍ يجعل الحصّةَ «بانتظار الاعتماد» (فاعتماد بعضه لا يكفي)؛ وحصّةٌ كلُّ إدخالاتها مرفوضةٌ تعود «لم يُدخَل»
    لأنّ المرفوضَ لا أثرَ له وعلى المعلّم أن يرصد من جديد.
    """
    states: dict[Any, str] = dict.fromkeys(session_ids, "none")
    if not session_ids:
        return states
    rows = (
        AttendanceEntry.objects.filter(session_id__in=session_ids, superseded_by__isnull=True)
        .values("session_id")
        .annotate(
            undecided=Count("id", filter=Q(decision__isnull=True)),
            approved=Count("id", filter=Q(decision__decision="approved")),
        )
    )
    for row in rows:
        if row["undecided"]:
            states[row["session_id"]] = "pending"
        elif row["approved"]:
            states[row["session_id"]] = "approved"
    return states


# ── إدخالاتُ المعلّم في شبكة المشرف (W-20261004-014) ─────────────────────────


@dataclass(frozen=True)
class EntryMark:
    """ما أدخله المعلّمُ لطالبٍ في حصّةٍ — يُعرض في خليّته بشبكة المشرف كما تعرضه صفحةُ المعلّم، بلا سببِ رفضٍ ولا نصٍّ حرّ.

    `can_decide`: أيملك هذا المستخدمُ الاعتمادَ الآن (الحاملُ يومَ الحصّة أو القيادةُ حين لا حامل، ولا يعتمد أحدٌ ما أدخله بنفسه).
    """

    entry_id: object
    state: str  # pending | approved | rejected
    status: str
    label: str
    minutes: int | None
    can_decide: bool
    corrected: bool


def _mark_of(entry: AttendanceEntry, can_decide: bool, corrected: bool) -> EntryMark:
    state, _reason = _state(entry)
    return EntryMark(
        entry_id=entry.id,
        state=state,
        status=str(entry.status),
        label=str(entry.get_status_display()),
        minutes=entry.tardiness_minutes,
        can_decide=can_decide and state == "pending",
        corrected=corrected,
    )


def entry_marks_of(
    class_group: Any, day: dt.date, user: CustomUser
) -> dict[object, dict[dt.time, EntryMark]]:
    """`{student_id: {start_time: EntryMark}}` لإدخالات المعلّمين في شعبةٍ ويومٍ — وحصّتا الزوج خانةٌ واحدة.

    مصدرُها واحدٌ مع صفحة المعلّم (`AttendanceEntry` الرأسُ غيرُ المُستبدَل ثمّ قرارُه) فلا منطقَ ثانياً للحالة؛ والأهليّةُ من
    `can_approve` نفسِها مخزَّنةً بالحصّة والمدخِل فلا استعلامَ لكلّ طالب.
    """
    heads = (
        AttendanceEntry.objects.filter(
            session__class_group=class_group, session__date=day, superseded_by__isnull=True
        )
        .select_related("decision", "session__class_group__wing", "entered_by")
        .order_by("session__start_time", "entered_at")
    )
    corrected = set(
        StudentAttendance.objects.filter(
            session__class_group=class_group, session__date=day, unobserved_correction__isnull=False
        ).values_list("student_id", "session__start_time")
    )
    verdicts: dict[tuple[object, object], bool] = {}
    marks: dict[object, dict[dt.time, EntryMark]] = {}
    for entry in heads:
        key = (entry.session_id, entry.entered_by_id)
        if key not in verdicts:
            verdicts[key] = bool(can_approve(user, entry.session, entered_by=entry.entered_by))
        start = entry.session.start_time
        marks.setdefault(entry.student_id, {}).setdefault(
            start, _mark_of(entry, verdicts[key], (entry.student_id, start) in corrected)
        )
    return marks


def entry_mark_of(entry_id: Any, user: CustomUser) -> EntryMark:
    """علامةُ إدخالٍ واحدٍ بعد قرارٍ — تُجلَب من جديدٍ فلا يبقى قرارٌ مخزَّنٌ قديم، ويُعاد رسمُها وحدَها (HTMX) في الشبكة."""
    entry = AttendanceEntry.objects.select_related(
        "decision", "session__class_group__wing", "entered_by"
    ).get(pk=entry_id)
    can = bool(can_approve(user, entry.session, entered_by=entry.entered_by))
    corrected = StudentAttendance.objects.filter(
        session=entry.session, student_id=entry.student_id, unobserved_correction__isnull=False
    ).exists()
    return _mark_of(entry, can, corrected)


def pending_decidable_count(marks: dict[object, dict[dt.time, EntryMark]]) -> int:
    """كم إدخالاً معلَّقاً يملك هذا المستخدمُ قرارَه في هذه العلامات — لسطر «ينتظر اعتمادك»."""
    return sum(1 for per_student in marks.values() for m in per_student.values() if m.can_decide)


def entry_grid_context(class_group: Any, day: dt.date, user: CustomUser) -> dict[str, Any]:
    """سياقُ شبكة المشرف من إدخالات المعلّمين: علاماتُ الخلايا وعدّادُ ما ينتظر قرارَ هذا المستخدم — بمفتاحَين لا غير."""
    marks = entry_marks_of(class_group, day, user)
    return {"entry_marks": marks, "awaiting_decision": pending_decidable_count(marks)}

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

from django.db.models import Count
from django.utils import timezone

from core.models import StudentEnrollment

from .attendance_entries import EVIDENCE_TYPES, PendingRow, unapproved_report
from .attendance_policy import approval_holder, can_approve, can_enter, holder_gap
from .models import AttendanceDecision, AttendanceEntry, Session, StudentAttendance

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
    verdicts: dict[tuple[object, object, str], bool] = {}
    items = []
    for entry in pending:
        key = (entry.session_id, entry.entered_by_id, entry.origin)
        if key not in verdicts:
            verdicts[key] = bool(
                can_approve(
                    user, entry.session, entered_by=entry.entered_by, entry_origin=entry.origin
                )
            )
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
class SessionGroup:
    """حصّةٌ واحدةٌ في الطابور: كلُّ ما أدخله المعلّمُ فيها ينتظر قرارَ المشرف دفعةً واحدة.

    المشرفُ يعتمد **حصّةً** لا طالباً: الحاضرون عدٌّ وحدَه، والغائبون والمتأخّرون وغيرُهم (`exceptions`) هم
    ما يُنظر فيه بنداً بنداً ويُرفض بسببٍ (أمرُ المالك 2026-10-06: لا بطاقةَ لكلّ طالب).
    """

    session: Session
    items: list[QueueItem]
    present: int
    exceptions: list[QueueItem]
    entered_by: Any
    age_hours: float
    as_leadership: bool
    #: «حاضرٌ افتراضيّ» كتبه الحفظُ لخلايا فارغةٍ — لا يدخل «اعتمادَ الحصّة» ولا يُعدّ حاضراً مرصوداً؛ له إجراءٌ منفصلٌ بتأكيد.
    defaults: int = 0

    @property
    def total(self) -> int:
        return len(self.items)

    @property
    def regular(self) -> int:
        """ما يعتمده «اعتمادُ الحصّة»: كلُّ الإدخالات عدا الافتراضيّ."""
        return len(self.items) - self.defaults


def approval_groups(user: CustomUser, school: School) -> list[SessionGroup]:
    """الطابورُ مجموعاً بالحصّة (الأقدمُ أوّلاً) — اعتمادٌ واحدٌ لحصّةٍ كاملة، وبنودٌ مستقلّةٌ لما يخرج عن الحاضر."""
    by_session: dict[Any, list[QueueItem]] = {}
    for item in approval_queue(user, school):
        by_session.setdefault(item.entry.session_id, []).append(item)
    groups = []
    for items in by_session.values():
        exceptions = [i for i in items if i.entry.status != "present"]
        defaults = sum(1 for i in items if i.entry.origin == "grid_default")
        groups.append(
            SessionGroup(
                session=items[0].entry.session,
                items=items,
                defaults=defaults,
                present=len(items) - len(exceptions) - defaults,
                exceptions=exceptions,
                entered_by=items[0].entry.entered_by,
                age_hours=max(i.age_hours for i in items),
                as_leadership=any(i.as_leadership for i in items),
            )
        )
    groups.sort(key=lambda g: (-g.age_hours, str(g.session.class_group)))
    return groups


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


@dataclass(frozen=True)
class PendingMark:
    """رصدُ معلّمٍ (غائب/متأخّر) لطالبٍ في اليوم لم يُقرَّر فيه بعد — وسمٌ لا حالة."""

    student: CustomUser
    class_group: Any
    count: int


def pending_marks_by_student(
    school: School,
    day: dt.date,
    *,
    teacher_ids: Any = None,
    student_ids: Any = None,
) -> dict[object, PendingMark]:
    """رصدُ المعلّم بانتظار اعتماد المشرف في يومٍ — عددٌ لكلّ طالبٍ في استعلامٍ واحد (تقريرُ غياب اليوم، W-20261005-002).

    يُعدّ رأسُ الإدخال بلا قرارٍ بحالة غائب أو متأخّر فقط: الحاضرُ لا يُنبَّه إليه، والمعتمَدُ في `StudentAttendance`، والمرفوضُ
    لا أثرَ له. وهو **وسمٌ لا احتساب**: المبدئيُّ لا يُحتسب غياباً قبل الاعتماد (D-125م) فلا يدخل في أيّ عدّ.
    النطاقُ كنطاق التقرير: `teacher_ids` معلّمو القسم، و`student_ids` طلبةُ الجناح؛ و`None` بلا قيد.
    """
    entries = (
        AttendanceEntry.objects.filter(
            school=school,
            session__date=day,
            superseded_by__isnull=True,
            decision__isnull=True,
            status__in=("absent", "late"),
        )
        .exclude(session__status="cancelled")
        .select_related("student", "session__class_group")
    )
    if teacher_ids is not None:
        entries = entries.filter(session__teacher_id__in=teacher_ids)
    if student_ids is not None:
        entries = entries.filter(student_id__in=student_ids)
    marks: dict[object, PendingMark] = {}
    for entry in entries:
        seen = marks.get(entry.student_id)
        marks[entry.student_id] = PendingMark(
            entry.student,
            seen.class_group if seen else entry.session.class_group,
            (seen.count if seen else 0) + 1,
        )
    return marks


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
    verdicts: dict[tuple[object, object, str], bool] = {}
    marks: dict[object, dict[dt.time, EntryMark]] = {}
    for entry in heads:
        key = (entry.session_id, entry.entered_by_id, entry.origin)
        if key not in verdicts:
            verdicts[key] = bool(
                can_approve(
                    user, entry.session, entered_by=entry.entered_by, entry_origin=entry.origin
                )
            )
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


def teacher_entry_overrides(sessions: Any) -> list[tuple[Any, str, int | None]]:
    """`(طالب، غائب|متأخّر، دقائق)` لما أدخله المعلّمُ **معلَّقاً أو معتمَداً** في حصص خانة — يُفتح عليه كشفُ المشرف مُعبَّأً.

    واقعةُ 2026-10-05: بعد «اعتمادُ الكلّ» رُسمت الأزرارُ «حاضر» للجميع لأنّ الرصدَ المعتمَدَ مصدرُه المعلّم لا المشرف فلا يقرؤه `cells_of`.
    الحاضرُ لا يُملأ (الافتراضيُّ حاضر)؛ والمرفوضُ لا يُعرض.
    """
    entries = (
        AttendanceEntry.objects.filter(
            session__in=sessions, superseded_by__isnull=True, status__in=("absent", "late")
        )
        .exclude(decision__decision="rejected")
        .order_by("entered_at")
    )
    return [(e.student_id, str(e.status), e.tardiness_minutes) for e in entries]


def held_student_ids(sessions: Any) -> set[Any]:
    """معرّفاتُ من له إدخالُ معلّمٍ **معلَّقٌ أو معتمَد** (رأسُ السلسلة ولو لم يُرفض) في حصص الخانة — لا يمسّه تثبيتُ المشرف."""
    return set(
        AttendanceEntry.objects.filter(session__in=sessions, superseded_by__isnull=True)
        .exclude(decision__decision="rejected")
        .values_list("student_id", flat=True)
    )


def exit_conflicts_of(sessions: Any, marks: dict) -> set[str]:
    """طلابٌ وسمهم المشرفُ **غائباً بنفسه** (بلا أن يرى خروجَهم: لا `exit`) ولهم خروجٌ مسجَّلٌ في هذه الحصّة — تعارضٌ لا يُثبَّت.

    الغيابُ المشتقُّ من الخروج نفسِه (يحمل `exit`) مشروعٌ: هو «غائبٌ بإذن المعلّم». والممنوعُ أن يُثبَّت غيابٌ عاديٌّ فوق خروجٍ لم يُنظر إليه.
    """
    from operations.class_exit import is_unreturned
    from operations.models import ClassExit

    manual = {
        str(student): mark
        for student, mark in marks.items()
        if mark.get("status") == "absent" and not mark.get("exit")
    }
    if not manual:
        return set()
    return {
        str(exit_.student_id)
        for exit_ in ClassExit.objects.filter(
            session__in=sessions, student_id__in=list(manual)
        ).select_related("session")
        if exit_.returned_at is None or is_unreturned(exit_)
    }


# ══════════════════════════════════════════════════════════════════
# جدولُ الشعبة العموديّ (W-20261006-005) — رؤوسُ السلاسل وسجلُّ الخليّة
# ══════════════════════════════════════════════════════════════════


@dataclass(frozen=True)
class ColumnCell:
    """رأسُ سلسلة خليّةٍ (حصّة، طالب): الأحدثُ يظهر والأقدمُ في السجلّ (D-239م). حالتُه وسمٌ لا حضورٌ معتمَد."""

    head_id: str
    status: str
    minutes: int | None
    state: str  # pending | approved | rejected
    default_present: bool
    entered_by_name: str
    entered_at: dt.datetime
    depth: int


@dataclass(frozen=True)
class CellHistoryRow:
    """سطرٌ من سجلّ الخليّة: من كتب ومتى ومن صحّح (القديمُ أوّلاً)."""

    status: str
    minutes: int | None
    entered_by_name: str
    entered_at: dt.datetime
    reason: str
    state: str
    default_present: bool


def column_heads(session_ids: list[Any]) -> dict[tuple[Any, Any], ColumnCell]:
    """`{(حصّة، طالب): رأسُ السلسلة}` لعدّة حصصٍ باستعلامٍ واحد — لا استعلامَ لكلّ خليّة (ثابتٌ بعدد الطلبة)."""
    heads = AttendanceEntry.objects.filter(
        session_id__in=session_ids, superseded_by__isnull=True
    ).select_related("decision", "entered_by")
    cells: dict[tuple[Any, Any], ColumnCell] = {}
    for entry in heads:
        state, _reason = _state(entry)
        cells[(entry.session_id, entry.student_id)] = ColumnCell(
            head_id=str(entry.pk),
            status=entry.status,
            minutes=entry.tardiness_minutes,
            state=state,
            default_present=entry.origin == "grid_default",
            entered_by_name=entry.entered_by.full_name,
            entered_at=entry.entered_at,
            depth=1 if entry.supersedes_id is None else 2,
        )
    return cells


def column_head(session: Session, student: CustomUser) -> ColumnCell | None:
    """رأسُ خليّةٍ واحدة (بعد كتابتها أو عند ردّ التعارض)."""
    return column_heads([session.pk]).get((session.pk, student.pk))


def cell_history(session: Session, student: CustomUser) -> list[CellHistoryRow]:
    """سلسلةُ الخليّة كاملةً — من كتب ومتى ومن صحّح. بلا PII سوى اسم الكاتب لمن يراه في مدرسته."""
    chain = list(
        AttendanceEntry.objects.filter(session=session, student=student)
        .select_related("decision", "entered_by")
        .order_by("entered_at")
    )
    replaced = {entry.supersedes_id for entry in chain if entry.supersedes_id}
    rows = []
    for entry in chain:
        state, _reason = _state(entry)
        if entry.pk in replaced:
            state = "superseded"
        rows.append(
            CellHistoryRow(
                status=entry.status,
                minutes=entry.tardiness_minutes,
                entered_by_name=entry.entered_by.full_name,
                entered_at=entry.entered_at,
                reason=entry.correction_reason,
                state=state,
                default_present=entry.origin == "grid_default",
            )
        )
    return rows


def self_approval_counts(school: School, day: dt.date) -> list[int]:
    """عددُ ما اعتمده كلُّ حاملِ جناحٍ بنفسه (`wing_holder_self`) في اليوم — أعدادٌ مرتَّبةٌ تنازليّاً **بلا أسماء** (ملخّصُ القيادة، D-239م)."""
    rows = (
        AttendanceDecision.objects.filter(
            school=school, basis="wing_holder_self", decided_at__date=day
        )
        .values("decided_by")
        .annotate(n=Count("id"))
        .order_by("-n")
    )
    return [row["n"] for row in rows]


def entry_tallies_by_start(class_group: Any, day: dt.date) -> dict[dt.time, dict[str, int]]:
    """ما أُدخل لشعبةٍ في يومٍ من جدول الشعبة/كشف المعلّم: لكلّ خانةٍ (بدء الحصّة) عددُ الحاضر والغائب والمتأخّر من **رأس** كلّ طالب.

    لوحةُ مشرف الجناح تقرؤه إلى جانب التثبيت القديم (`PeriodConfirmation`) لأنّ مسار الجدول لا يكتب التثبيتَ (W-20261008-003، الخيار أ). استعلامٌ واحد؛
    ويحسب الإدخالَ المعلَّق والمعتمَدَ معاً (المبدئيُّ إدخالٌ يعرفه المشرفُ ويعتمده) — ولا يُحتسب حضوراً ولا غياباً في التقارير.
    """
    rows = (
        AttendanceEntry.objects.filter(
            session__class_group=class_group, session__date=day, superseded_by__isnull=True
        )
        .exclude(session__status="cancelled")
        .values("session__start_time", "status")
        .annotate(n=Count("id"))
    )
    out: dict[dt.time, dict[str, int]] = {}
    for row in rows:
        tally = out.setdefault(row["session__start_time"], {"present": 0, "absent": 0, "late": 0})
        if row["status"] in tally:
            tally[row["status"]] += row["n"]
    return out

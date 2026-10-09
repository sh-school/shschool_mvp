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

from django.db.models import Count

from .models import AttendanceEntry, Session

if TYPE_CHECKING:
    from core.models import CustomUser, School


def _state(entry: AttendanceEntry | None) -> tuple[str, str]:
    if entry is None:
        return "none", ""
    decision = getattr(entry, "decision", None)
    if decision is None:
        return "pending", ""
    return str(decision.decision), str(decision.reason)


@dataclass(frozen=True)
class GridColumn:
    session: Session
    number: int
    is_focus: bool


def day_entry_heads(school: School, day: dt.date) -> list[tuple[Any, Any, dt.time, bool]]:
    """رؤوسُ إدخالات الجدول في يومٍ: `(طالب، شعبة، بدء الخانة، أبلا قرارٍ؟)` — لمُجمِّع يوم المدرسة (W-20261008-004).

    قراءةُ **وجودٍ وعدٍّ** لا حالة: الخانةُ التي لها رأسُ إدخالٍ «مسجَّلةٌ» (فمسارُ الجدول لا يكتب `PeriodConfirmation`)، والطالبُ ذو الرأس بلا قرارٍ
    «معلَّق» يُعدّ ولا يُحتسب حاضراً ولا غائباً (D-125م). فلا يُقرأ المبدئيُّ هنا حضوراً ولا غياباً.
    """
    rows = AttendanceEntry.objects.filter(
        school=school, session__date=day, superseded_by__isnull=True
    ).values_list("student_id", "session__class_group_id", "session__start_time", "decision__id")
    return [
        (student, section, start, decision is None) for student, section, start, decision in rows
    ]


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

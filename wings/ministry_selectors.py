"""ملخّصُ الحصّتين الأولى والثانية للرفع في نظام الوزارة — الشعبةُ صفّاً والجناحُ والمدرسةُ مجاميع.

الرفعُ يدويٌّ في نظام الوزارة خارجَ المنصّة (قرارُ 2026-09-13 وأمرُ المالك 2026-10-06)؛ فالمنصّةُ تُعدّ
له ما يحتاجه من مكانٍ واحد: كم طالباً غاب **الحصّتين معاً** في كلّ شعبةٍ (بلا عذرٍ وبعذر)، ومن غاب إحداهما،
ومن تأخّر، ومن بقي بلا رصدٍ فلا يُحكم عليه، ثمّ أسماءُ من يُرفعون. وهو **للقراءة**: لا يغيّر رصداً ولا يعتمده.

* **الحصّتان الأولى والثانية** بترتيب خانات الشعبة في يومها (كتقرير «غياب اليوم» نفسِه) — لا بالرقم المطبوع في الجرس.
* **لا يُرفع طالبٌ على رصدٍ ناقص:** من لم تُرصد إحدى حصّتيه «بلا رصد» ولا يدخل أيَّ عدّ للغياب.
* **المبدئيُّ لا يُحتسب** (D-125م): رصدُ المعلّم بانتظار اعتماد المشرف يُعدّ وسماً «بانتظار الاعتماد» لا غياباً.
* **لا رقمَ شخصيّاً** في أيّ مخرَج (قرارُ 2026-09-13).
* **النطاق:** `student_ids` طلبةُ المقيَّد بجناحه؛ و`None` للقيادة وللمدرسة كلِّها.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from typing import Any

from core.academic_calendar import academic_year_for_school
from core.models import ClassGroup, StudentEnrollment
from core.models.academic import grade_order
from operations.attendance_selectors import pending_marks_by_student
from operations.models import Session, StudentAttendance

#: حصّتا الرفع: الأولى والثانية بترتيب الخانات.
PERIODS = 2


@dataclass
class Counts:
    """مجاميعُ شعبةٍ أو صفٍّ أو مدرسة — حقولٌ تُجمع."""

    enrolled: int = 0
    absent_both_unexcused: int = 0
    absent_both_excused: int = 0
    absent_one: int = 0
    late: int = 0
    unrecorded: int = 0
    pending: int = 0

    @property
    def absent_both(self) -> int:
        return self.absent_both_unexcused + self.absent_both_excused

    def add(self, other: Counts) -> None:
        for name in (
            "enrolled",
            "absent_both_unexcused",
            "absent_both_excused",
            "absent_one",
            "late",
            "unrecorded",
            "pending",
        ):
            setattr(self, name, getattr(self, name) + getattr(other, name))


@dataclass
class ClassRow:
    group: Any
    counts: Counts
    #: الشعبةُ بلا حصّتين في هذا اليوم — لا يُحكم عليها (عطلةٌ، أو شعبةٌ لا جدولَ لها).
    has_periods: bool


@dataclass
class GradeRow:
    label: str
    counts: Counts
    rows: list[ClassRow] = field(default_factory=list)
    #: رمزُ الصفّ (G8…) — مفتاحُ الترشيح لا نصُّ العرض.
    key: str = ""


@dataclass(frozen=True)
class Ministered:
    """طالبٌ يُرفع غائباً — بلا رقمٍ شخصيّ."""

    name: str
    class_code: str
    excused: bool
    grade: str = ""


@dataclass
class MinistrySummary:
    day: dt.date
    grades: list[GradeRow]
    total: Counts
    ministered: list[Ministered]
    notes: list[str] = field(default_factory=list)

    @property
    def class_rows(self) -> list[ClassRow]:
        return [row for grade in self.grades for row in grade.rows]

    @property
    def has_unrecorded(self) -> bool:
        return self.total.unrecorded > 0


def _current_enrollments(groups: list[Any], student_ids: Any) -> dict[Any, list[Any]]:
    """طلبةُ كلّ شعبة بقيدهم **الجاري**: من حمل قيدين نشطين يُعدّ في أحدثهما وحدَه."""
    rows = (
        StudentEnrollment.objects.filter(is_active=True, class_group__in=groups)
        .select_related("student")
        .order_by("student_id", "-enrolled_at", "-id")
    )
    if student_ids is not None:
        rows = rows.filter(student_id__in=student_ids)
    seen: set[Any] = set()
    by_class: dict[Any, list[Any]] = {}
    for enrollment in rows:
        if enrollment.student_id in seen:
            continue
        seen.add(enrollment.student_id)
        by_class.setdefault(enrollment.class_group_id, []).append(enrollment.student)
    return by_class


def _first_slots(school: Any, day: dt.date, group_ids: list[Any]) -> dict[Any, list[dt.time]]:
    """خانتا كلّ شعبةٍ الأولى والثانية بترتيب الساعة — من حصصها غيرِ الملغاة في اليوم."""
    starts: dict[Any, set[dt.time]] = {}
    sessions = (
        Session.objects.filter(school=school, date=day, class_group_id__in=group_ids)
        .exclude(status="cancelled")
        .values_list("class_group_id", "start_time")
    )
    for group_id, start in sessions:
        starts.setdefault(group_id, set()).add(start)
    return {gid: sorted(times)[:PERIODS] for gid, times in starts.items()}


def _marks(
    school: Any, day: dt.date, slots: dict[Any, list[dt.time]]
) -> dict[tuple[Any, Any], dict[dt.time, tuple[str, bool]]]:
    """حالُ كلّ (طالب، شعبة) في خانتيه: الحاضرُ أو المتأخّرُ في إحدى حصّتَي الخانة يغلب ما سواه — كتقرير اليوم."""
    wanted = {gid: set(times) for gid, times in slots.items()}
    rows = StudentAttendance.objects.filter(
        school=school, session__date=day, session__class_group_id__in=list(wanted)
    ).values_list(
        "student_id",
        "session__class_group_id",
        "session__start_time",
        "status",
        "excuse_type",
    )
    out: dict[tuple[Any, Any], dict[dt.time, tuple[str, bool]]] = {}
    for student_id, group_id, start, status, excuse in rows:
        if start not in wanted[group_id]:
            continue
        cell = out.setdefault((student_id, group_id), {})
        current = cell.get(start)
        if (
            current is None
            or current[0] not in ("present", "late")
            or status in ("present", "late")
        ):
            cell[start] = (status, bool(excuse))
    return out


def _row_counts(
    students: list[Any],
    group_id: Any,
    times: list[dt.time],
    marks: dict[tuple[Any, Any], dict[dt.time, tuple[str, bool]]],
    pending: dict[Any, Any],
    ministered: list[Ministered],
    class_code: str,
    grade_key: str,
) -> Counts:
    counts = Counts(enrolled=len(students))
    for student in students:
        if student.id in pending:
            counts.pending += 1
        cell = marks.get((student.id, group_id), {})
        picked = [cell.get(start) for start in times]
        if len(picked) < PERIODS or any(p is None for p in picked):
            counts.unrecorded += 1
            continue
        statuses = [p[0] for p in picked if p is not None]
        if all(s == "absent" for s in statuses):
            excused = all(p[1] for p in picked if p is not None)
            if excused:
                counts.absent_both_excused += 1
            else:
                counts.absent_both_unexcused += 1
            ministered.append(Ministered(student.full_name, class_code, excused, grade_key))
        elif "absent" in statuses:
            counts.absent_one += 1
        elif "late" in statuses:
            counts.late += 1
    return counts


def _notes(total: Counts) -> list[str]:
    """تنبيهاتُ الملخّص من مجاميعه — بلا رصدٍ وبانتظار الاعتماد."""
    notes: list[str] = []
    if total.unrecorded:
        notes.append(f"{total.unrecorded} طالباً بلا رصدٍ في إحدى الحصّتين — لا يُرفعون حتّى يُرصدوا.")
    if total.pending:
        notes.append(
            f"{total.pending} طالباً لهم رصدُ معلّمٍ بانتظار الاعتماد — لا يدخل في أيّ عدٍّ حتّى يُعتمد."
        )
    return notes


def grade_choices(summary: MinistrySummary) -> list[tuple[str, str]]:
    """(رمزُ الصفّ، نصُّه) لقائمة الترشيح — بترتيب الصفوف في الملخّص."""
    return [(grade.key, grade.label) for grade in summary.grades if grade.key]


def narrow(summary: MinistrySummary, *, grade: str = "", q: str = "") -> MinistrySummary:
    """ملخّصٌ مضيَّقٌ بصفٍّ و/أو بحثٍ في الشعبة أو اسم الطالب — والمجاميعُ تُعاد من الصفوف الباقية.

    فما يراه المستخدمُ في الجدول والأرقام والتصدير شيءٌ واحد: ترشيحٌ لا يطابق مجموعَه. والبحثُ باسمِ طالبٍ
    يُبقي شعبتَه وحدَها، وبرمز شعبةٍ يُبقي الشعبةَ وأسماءَ من يُرفعون منها.
    """
    needle = (q or "").strip()
    if not grade and not needle:
        return summary
    in_scope = [g for g in summary.grades if not grade or g.key == grade]
    scope_codes = {row.group.short_code for g in in_scope for row in g.rows}
    by_name = {m.class_code for m in summary.ministered if needle and needle in m.name}
    ministered = [
        m
        for m in summary.ministered
        if m.class_code in scope_codes
        and (not needle or needle in m.name or needle in m.class_code)
    ]
    grades: list[GradeRow] = []
    total = Counts()
    for source in in_scope:
        rows = [
            row
            for row in source.rows
            if not needle or needle in row.group.short_code or row.group.short_code in by_name
        ]
        if not rows:
            continue
        counts = Counts()
        for row in rows:
            counts.add(row.counts)
        grades.append(GradeRow(source.label, counts, rows, source.key))
        total.add(counts)
    return MinistrySummary(summary.day, grades, total, ministered, _notes(total))


def ministry_summary(school: Any, day: dt.date, *, student_ids: Any = None) -> MinistrySummary:
    """ملخّصُ الحصّتين الأولى والثانية لمدرسةٍ في يوم — للمدرسة كلِّها أو لطلبة جناحٍ بعينهم."""
    year = academic_year_for_school(school)
    groups = list(
        ClassGroup.objects.filter(school=school, academic_year=year, is_active=True)
        .select_related("wing")
        .order_by(grade_order("grade"), "section")
    )
    group_ids = [g.id for g in groups]
    by_class = _current_enrollments(groups, student_ids)
    slots = _first_slots(school, day, group_ids)
    marks = _marks(school, day, slots)
    pending = pending_marks_by_student(school, day, student_ids=student_ids)

    ministered: list[Ministered] = []
    grades: dict[str, GradeRow] = {}
    total = Counts()
    for group in groups:
        students = by_class.get(group.id, [])
        if student_ids is not None and not students:
            continue  # شعبةٌ لا طالبَ فيها من نطاقه — لا تظهر في ملخّصه
        times = slots.get(group.id, [])
        has_periods = len(times) >= PERIODS
        counts = (
            _row_counts(
                students, group.id, times, marks, pending, ministered, group.short_code, group.grade
            )
            if has_periods
            else Counts(enrolled=len(students))
        )
        label = group.get_grade_display() if hasattr(group, "get_grade_display") else group.grade
        grade = grades.setdefault(group.grade, GradeRow(str(label), Counts(), key=group.grade))
        grade.rows.append(ClassRow(group, counts, has_periods))
        grade.counts.add(counts)
        total.add(counts)

    ministered.sort(key=lambda m: (m.class_code, m.name))
    return MinistrySummary(day, list(grades.values()), total, ministered, _notes(total))


def summary_for_request(request: Any, day: dt.date) -> tuple[MinistrySummary, bool]:
    """ملخّصُ طالب الطلب بنطاقه: (الملخّص، أمقيَّدٌ بجناحه وحدَه؟).

    المشرفُ لطلبة جناحه، وحاصرُ الغياب العامّ (مقيَّدٌ بالأجنحة الخمسة) والقيادةُ للمدرسة كلِّها — فالعنوانُ «طلبةُ جناحك»
    للأوّل وحدَه.
    """
    from .scope import student_scope_for
    from .services import holds_school_wide

    scope = student_scope_for(request)
    summary = ministry_summary(
        request.school, day, student_ids=scope.student_ids() if scope.is_wing_bound else None
    )
    return summary, scope.is_wing_bound and not holds_school_wide(request.user)


def dashboard_figures(user: Any, school: Any, day: dt.date) -> Counts:
    """أرقامُ الحصّتين الأولى والثانية لرأس لوحة المشرف — مجاميعُ بلا أسماء (PDPPL: تقليلُ البيانات).

    النطاقُ نطاقُ الطلبة نفسُه كالملخّص: المشرفُ لطلبة جناحه، وحاصرُ الغياب العامّ والقيادةُ للمدرسة كلِّها.
    """
    from .scope import student_scope

    scope = student_scope(user, school)
    return ministry_summary(
        school, day, student_ids=scope.student_ids() if scope.is_wing_bound else None
    ).total

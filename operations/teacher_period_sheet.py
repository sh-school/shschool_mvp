"""كشفُ الحصّة للمعلّم الفعليّ — **القالبُ نفسُه** الذي يرسم به المشرفُ كشفَه (W-20261004-015، أمرُ المالك: نسخةٌ طبقُ الأصل مع أنّ المعلّم يرصد حصّتَه).

القالبُ المشتركُ `attendance/period_sheet.html` يتوقّع سياقاً واحداً؛ وللمشرف يبنيه `wings.views.record_section`، وللمعلّم تبنيه هذه الوحدةُ
مقتصرةً على **حصصه** في شعبة الحصّة المفتوحة (أعمدةٌ: حصصُه اليومَ فقط). والفرقُ في الخدمة وحدَها:

- المشرفُ: `confirm_period` ← `StudentAttendance` مباشرةً.
- المعلّم: `enter_period_marks` ← `AttendanceEntry` مبدئيّ ينتظر اعتمادَ الحامل (D-125م). والخروجُ `ClassExit` كما كان للمعلّم (لا `whereabouts`).

وهذه الوحدةُ لا تنشئ سياسةً: الإدخالُ والنافذةُ والقيدُ كلُّها `attendance_policy` عبر `submit_entry`.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any
from uuid import UUID

from django.db import transaction
from django.urls import reverse
from django.utils import timezone

from .attendance_entries import (
    ENTERABLE_STATUSES,
    EntryError,
    EntryRefusedError,
    submit_entry,
)
from .attendance_selectors import StudentLine, entry_closed_reason, entry_marks_of, student_lines
from .models import Session, StudentAttendance

if TYPE_CHECKING:
    from core.models import CustomUser

#: وجهاتُ خروج المعلّم الثلاث كما في زرّ «خرج بإذن» الأصليّ — لا تُعيَّن على وجهات المشرف الخمس؛ فالخروجُ سطرُ `ClassExit` يشتقّ منه كشفُ المشرف «غائب بإذن المعلّم».
TEACHER_EXIT_DESTINATIONS = [
    ("clinic", "العيادة"),
    ("admin", "الإدارة / المشرف"),
    ("restroom", "دورة المياه"),
]


@dataclass(frozen=True)
class TeacherPick:
    """ما تُفتح عليه خانةُ الطالب للمعلّم — بصيغة `period_register.Pick` نفسِها (يقرؤها القالبُ المشترك) وزيادة `locked`.

    `locked`: رصدٌ معتمَدٌ أو رصدُ المشرف لا يُغيَّر من هذا الكشف (تصحيحُ المعتمَد يلزمه سببٌ في نموذجه)، فتُعرض أزرارُه مقفلةً.
    """

    status: str = "present"
    whereabouts: str = ""
    marker: str = ""
    tap: int | None = None
    seen_exit: str = ""
    away_note: str = ""
    locked: bool = False
    out_since: int = 0
    exit_count: int = 0
    exit_base: int = 0
    exit_open_at: int = 0
    exit_note: str = ""


def _pick_of(line: StudentLine, destination: str, out_since: int, day: Any = None) -> TeacherPick:
    entry = line.entry
    if entry is not None and line.entry_state in ("pending", "approved"):
        return TeacherPick(
            status=str(entry.status),
            whereabouts=destination,
            locked=line.entry_state == "approved",
            out_since=out_since,
            **_exit_fields(day),
        )
    if line.effective_status:  # رصدُ مشرفٍ أو عيادةٍ أو بوّابة: لا يُكتب فوقه من هنا
        return TeacherPick(
            status=str(line.effective_status),
            whereabouts=destination,
            locked=True,
            out_since=out_since,
            **_exit_fields(day),
        )
    return TeacherPick(whereabouts=destination, out_since=out_since, **_exit_fields(day))


def _exit_fields(day: Any) -> dict[str, Any]:
    """ما يحمله زرُّ «خروج» من حساب اليوم (`exit_day_of`): عددُ المرّات، ومجموعُ المدّة قبل الخروج المفتوح، ولحظةُ بدئه."""
    if day is None:
        return {}
    open_left = day.open_left
    base = day.seconds - (day.open_span if open_left else 0)
    note = f"خرج {day.count} مرّة اليوم · المجموع {day.label}" if day.count else ""
    return {
        "exit_count": day.count,
        "exit_base": base,
        "exit_open_at": open_left,
        "exit_note": note,
    }


def _cells(class_group: Any, day: dt.date) -> dict:
    """ما رُصد فعلاً (أيَّ مصدرٍ) في خانات اليوم: `{student_id: {start_time: Cell}}` — لا مصدرُ المشرف وحدَه كما في `cells_of`."""
    from .period_register import Cell

    rows = (
        StudentAttendance.objects.filter(session__class_group=class_group, session__date=day)
        .values_list(
            "student_id", "session__start_time", "status", "whereabouts", "late_minutes", "exit_id"
        )
        .order_by("session__start_time")
    )
    cells: dict = {}
    for student_id, start, status, where, minutes, exit_id in rows:
        cells.setdefault(student_id, {}).setdefault(start, Cell(status, where, minutes, exit_id))
    return cells


def next_session_of(session: Session) -> Session | None:
    return (
        Session.objects.filter(
            school=session.school,
            teacher_id=session.teacher_id,
            date=session.date,
            start_time__gt=session.start_time,
        )
        .exclude(status="cancelled")
        .select_related("class_group")
        .order_by("start_time")
        .first()
    )


def teacher_sheet_context(user: CustomUser, session: Session) -> dict[str, Any]:
    """سياقُ الكشف المشترك لحصّة المعلّم (المفتاحُ نفسُه الذي يبنيه المشرف) — أعمدتُه حصصُه وحدَها."""
    from .class_exit import carry_over, exit_day_of, exits_of_session, root_of
    from .period_register import period_end, periods_of, teacher_outs_of, track_note

    klass = session.class_group
    day = session.date
    now = timezone.now()
    mine = [
        p
        for p in periods_of(klass, day)
        if any(s.teacher_id == session.teacher_id for s in p.sessions)
    ]
    focus = next((p for p in mine if any(s.id == session.id for s in p.sessions)), None)
    lines = student_lines(session)
    cells = _cells(klass, day)
    outs = teacher_outs_of(klass, day)
    ends = {p.start: period_end(day, p) for p in mine}
    carry_over(session, now)  # خروجُ من لم يعد من حصّةٍ سابقةٍ اليومَ يمتدّ هنا
    exits = exits_of_session(session)
    rows = []
    for line in lines:
        sid = line.student.id
        own = cells.get(sid, {})
        gone = outs.get(sid, {})
        current = exits.get(sid, (None, []))[0]
        destination = current.destination if current is not None else ""
        out_since = int(root_of(current).left_at.timestamp()) if current is not None else 0
        day_exit = exit_day_of(line.student, day, now)
        rows.append(
            {
                "student": line.student,
                "track": [
                    (p, own.get(p.start), track_note(gone.get(p.start), now, ends[p.start]))
                    for p in mine
                ],
                "cell": own.get(focus.start) if focus else None,
                "pick": _pick_of(line, destination, out_since, day_exit),
            }
        )
    following = next_session_of(session)
    closed = entry_closed_reason(user, session, lines)
    marks = entry_marks_of(klass, day, user)
    subject = (session.subject.name_ar if session.subject else "") or "حصة"
    return {
        "teacher_sheet": True,
        "klass": klass,
        "day": day,
        "heading": f"{subject} — {klass}",
        "subtitle": f"{day:%d/%m/%Y} · {session.start_time:%H:%M} · {len(rows)} طالباً",
        "periods": [(p, p.status(day, now)) for p in mine],
        "focus": focus,
        "focus_status": focus.status(day, now) if focus else "",
        "measured_now": bool(focus and focus.in_window(day, now)),
        "rows": rows,
        "whereabouts": TEACHER_EXIT_DESTINATIONS,
        "draft_key": f"tch:{session.id}:{len(rows)}",
        "following": following.class_group if following else None,
        "entry_marks": marks,
        "awaiting_decision": 0,
        "form_action": reverse("attendance_period_entries", args=[session.id]),
        "start_epoch": int(
            timezone.make_aware(dt.datetime.combine(session.date, session.start_time)).timestamp()
        ),
        "tab_urls": {
            p.key: reverse(
                "attendance",
                args=[next(s.id for s in p.sessions if s.teacher_id == session.teacher_id)],
            )
            for p in mine
        },
        "entry_closed": closed,
        "sheet_closed": bool(closed),
    }


def late_minutes(session: Session, mark: dict[str, str], now: dt.datetime) -> int | None:
    """دقائقُ التأخّر **آلياً كما في كشف المشرف**: داخل وقت الحصّة تُحسب من لحظة ضغط المعلّم على «متأخّر» (ساعةُ الجهاز مصحَّحةً بساعة الخادم
    في `t-<طالب>`) أو من لحظة التثبيت إن لم تصحّ — لا يكتب المعلّمُ وقتاً؛ وخارج وقت الحصّة (حتى خمس دقائق بعد نهايتها) تُكتب باليد.
    """
    from .period_register import GRACE, Period, _tapped
    from .tardiness import minutes_after_start

    start = timezone.make_aware(dt.datetime.combine(session.date, session.start_time))
    end = timezone.make_aware(dt.datetime.combine(session.date, session.end_time)) + GRACE
    if not start <= now <= end:
        typed = mark.get("late_minutes", "")
        return int(typed) if typed.isdigit() and int(typed) <= 240 else None
    period = Period(number=0, start=session.start_time, end=session.end_time, sessions=[])
    tapped = _tapped(mark.get("tapped_at"), session.date, period, now)
    return minutes_after_start(session, timezone.localtime(tapped or now))


@dataclass
class EnterResult:
    entered: int = 0
    exits: int = 0
    needs_reason: int = 0
    conflicts: int = 0
    refused: int = 0


def parse_marks(post: Any) -> dict[str, dict[str, str]]:
    """حقولُ النموذج المشترك `s-/w-/m-<طالب>` → `{طالب: {status, whereabouts, late_minutes}}` — كما يقرؤها `record_period` للمشرف."""
    marks: dict[str, dict[str, str]] = {}
    for key, value in post.items():
        for prefix, field in (
            ("s-", "status"),
            ("w-", "whereabouts"),
            ("m-", "late_minutes"),
            ("t-", "tapped_at"),
        ):
            if key.startswith(prefix):
                marks.setdefault(key.removeprefix(prefix), {})[field] = value
    return marks


def enter_period_marks(
    user: CustomUser,
    session: Session,
    student_ids: dict[UUID, CustomUser],
    marks: dict[str, dict[str, str]],
) -> EnterResult:
    """يحوّل اختياراتِ الكشف إلى إدخالاتٍ مبدئيّةٍ لحصّة المعلّم: لكلّ طالبٍ `submit_entry` بسياسته، والخروجُ `ClassExit`.

    - اختيارُ وجهةٍ (`w-`) يفتح خروجاً (`leave`) ولا يُدخَل له غيابٌ: المشرفُ يرى «غائب بإذن المعلّم» مشتقّاً من الخروج.
    - رصدٌ معتمَدٌ أو لرصد غيرِ المعلّم: لا يُكتب فوقه (تصحيحُه المسبَّب في نموذجه) — يُعدّ ولا يُسقط البقيّة.
    - المنعُ بالسياسة (`EntryRefusedError`) يُرفع كلُّه إلى المستدعي فيُلغى الطلبُ بلا إدخالٍ جزئيّ.
    """
    from .class_exit import close_for_absence, leave, open_exit

    result = EnterResult()
    now = timezone.now()
    with transaction.atomic():
        for raw_id, mark in marks.items():
            try:
                student = student_ids[UUID(raw_id)]
            except (ValueError, KeyError):
                continue
            where = mark.get("whereabouts", "")
            if where:
                leave(session, student, where, by=user)
                result.exits += 1
                continue
            status = mark.get("status", "")
            if status not in ENTERABLE_STATUSES:
                continue
            if status == "absent" and open_exit(session, student) is not None:
                close_for_absence(
                    session, student, now
                )  # غائبٌ وخروجٌ لا يجتمعان: وسمُ الغياب يُغلق الخروجَ المفتوح
                result.conflicts += 1
            minutes = late_minutes(session, mark, now) if status == "late" else None
            try:
                with transaction.atomic():
                    submit_entry(user, session, student, status, tardiness_minutes=minutes)
                result.entered += 1
            except EntryRefusedError:
                raise  # المنعُ بالسياسة يُلغي الطلبَ كلَّه
            except EntryError as error:
                if error.code == "unchanged":
                    continue
                if error.code in ("reason_required", "non_teacher_row"):
                    result.needs_reason += 1
                    continue
                raise
    return result

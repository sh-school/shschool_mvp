"""أثرُ «خرج بإذن» في كشفٍ ثبّته المشرف — عند الجرس، وعند العودة، وعند الإلغاء.

قرارُ المالك (2026-09-16): لا «حاضر» كاذب ولا «هروب» كاذب، ولا نقرةَ زائدةً على المشرف.
والمشرفُ يثبّت الحصصَ من الثانية في **بدئها**، فخروجٌ يقع بعد تثبيته لا يراه. فهنا:

- **عند نهاية الحصّة** (`finalize_exits_for_day`، مهمّةٌ كلَّ خمس دقائق): يُغلق كلُّ
  خروجٍ بقي مفتوحاً بلحظة الجرس، ومن لم يعد في حصّةٍ **مثبّتةٍ** وخانتُه حاضرٌ أو
  متأخّرٌ لا تحسب هذا الخروج تُكتب «غائب · مكانُه» بسطرٍ في سجلّ المراجعة، وتُعاد
  مخالفاتُ اليوم الآليّة (تزول مخالفةُ التأخّر، ولا هروبَ مع الإذن). والحصّةُ غيرُ
  المثبّتة لا يُكتب فيها شيء: الكشفُ يعرض الخروجَ حين يثبّتها المشرف.
- **عند العودة قبل الجرس أو إلغاء الخروج** (`revert_derived_absence`): الغيابُ الذي
  اشتُقّ من **هذا** الخروج (`StudentAttendance.exit`) يرجع حاضراً. وغيابٌ قاله المشرفُ
  بنفسه (بلا خروجٍ محسوب) لا يُمسّ أبداً.

وكلُّه ثابتُ التكرار: الخانةُ التي تحسب الخروجَ تُترك في المرّة الثانية.
"""

from __future__ import annotations

import datetime as dt
import logging
from typing import Any

from django.db import transaction
from django.utils import timezone

from core.models import AuditLog
from operations.class_exit import WHEREABOUTS_OF, close_unreturned, is_unreturned, session_end
from operations.day_attendance import SOURCE
from operations.models import ClassExit, PeriodConfirmation, StudentAttendance
from operations.period_register import (
    ATTENDED,
    Period,
    _sync_rule,
    _warn_of_gates,
    period_end,
    periods_of,
    sync_escapes,
)

logger = logging.getLogger(__name__)


def exit_overrides(status: str, cell_exit_id: Any, exit_: ClassExit) -> bool:
    """خانةٌ حاضرةٌ أو متأخّرةٌ لم تحسب هذا الخروج — فيقلبها الخروجُ غياباً بإذن."""
    return status in ATTENDED and cell_exit_id != exit_.pk


def audit_cell_change(
    user: Any,
    school: Any,
    student: Any,
    session: Any,
    *,
    before: dict,
    after: dict,
    why: str,
    exit_: ClassExit | None = None,
) -> None:
    """سطرٌ في سجلّ المراجعة لكلّ تبديلٍ لم تُجرِه يدُ المشرف — كأخواته في `undo.py`."""
    AuditLog.objects.create(
        user=user,
        school=school,
        action="update",
        model_name="other",
        object_id=str(session.pk),
        object_repr=f"أثرُ الخروج بإذن في الكشف — {student.full_name} · {session}"[:300],
        changes={
            "student": str(student.pk),
            "before": before,
            "after": after,
            "exit": str(exit_.pk) if exit_ is not None else None,
            "why": why,
            "automatic": user is None,
        },
    )


def refresh_counts(class_group: Any, day: dt.date, period: Period) -> None:
    """أعدادُ التثبيت من سطوره — بعد تبديلٍ جرى خارجَه."""
    statuses: dict = {}
    for student_id, status in StudentAttendance.objects.filter(
        session__in=period.sessions, source=SOURCE
    ).values_list("student_id", "status"):
        statuses.setdefault(student_id, status)
    values = list(statuses.values())
    PeriodConfirmation.objects.filter(
        class_group=class_group, date=day, start_time=period.start
    ).update(
        present_count=values.count("present"),
        absent_count=values.count("absent"),
        late_count=values.count("late"),
    )


@transaction.atomic
def reflect_period_exits(class_group: Any, day: dt.date, period: Period, now: dt.datetime) -> int:
    """نهايةُ حصّةٍ واحدة: يُغلق خروجَها المفتوح، ويقلب الحاضرَ الذي لم يحسبه — ويُرجع عددَ ما قُلب."""
    if now < period_end(day, period):
        return 0
    for session in period.sessions:
        close_unreturned(session, now=now)
    if period.confirmation is None:
        return 0

    latest: dict = {}
    for exit_ in (
        ClassExit.objects.filter(session__in=period.sessions)
        .select_related("session", "student")
        .order_by("left_at")
    ):
        if is_unreturned(exit_):
            latest[exit_.student_id] = exit_
    if not latest:
        return 0

    rows_of: dict = {}
    for row in StudentAttendance.objects.filter(
        session__in=period.sessions, student_id__in=latest, source=SOURCE
    ).select_related("session"):
        rows_of.setdefault(row.student_id, []).append(row)

    flipped = []
    for student_id, exit_ in latest.items():
        rows = rows_of.get(student_id)
        if not rows or not exit_overrides(rows[0].status, rows[0].exit_id, exit_):
            continue
        where = WHEREABOUTS_OF.get(exit_.destination, "out_permit")
        was_late = any(row.status == "late" for row in rows)
        audit_cell_change(
            None,
            class_group.school,
            exit_.student,
            rows[0].session,
            before={"status": rows[0].status, "whereabouts": rows[0].whereabouts},
            after={"status": "absent", "whereabouts": where},
            why="خرج بإذن المعلّم ولم يعد حتى نهاية الحصّة",
            exit_=exit_,
        )
        StudentAttendance.objects.filter(pk__in=[row.pk for row in rows]).update(
            status="absent",
            whereabouts=where,
            late_minutes=None,
            exit=exit_,
            updated_at=now,
        )
        if was_late:
            _sync_rule(
                class_group.school,
                exit_.student,
                "period_tardy",
                set(),
                {period.start: period},
                None,
                scope=period.sessions,
            )
        flipped.append(exit_.student)

    if flipped:
        # المخالفةُ الآليّةُ تحتاج راصداً: من ثبّت الحصّة — النظامُ لا يوقّع مخالفة.
        sync_escapes(class_group, day, period.confirmation.confirmed_by)
        refresh_counts(class_group, day, period)
        _warn_of_gates(class_group.school, flipped, day)
    return len(flipped)


def finalize_exits_for_day(school: Any, day: dt.date, now: dt.datetime | None = None) -> int:
    """كلُّ حصّةٍ انتهت اليومَ وفيها خروجٌ لم يعد صاحبُه — ويُرجع عددَ الخانات المقلوبة.

    اليومُ كلُّه نافذةُ أمان: مهمّةٌ فاتتها دورةٌ تُدركها في التالية. وكلُّ شعبةٍ في
    معاملتها، فعطبُ واحدةٍ لا يُسقط غيرَها.
    """
    now = now or timezone.now()
    slots: dict = {}
    for exit_ in (
        ClassExit.objects.filter(school=school, session__date=day)
        .exclude(session__status="cancelled")
        .select_related("session", "session__class_group")
    ):
        if session_end(exit_.session) > now:
            continue
        if exit_.returned_at is not None and not is_unreturned(exit_):
            continue
        group = exit_.session.class_group
        slots.setdefault(group.pk, (group, set()))[1].add(exit_.session.start_time)

    flipped = 0
    for group, starts in slots.values():
        try:
            for period in periods_of(group, day):
                if period.start in starts:
                    flipped += reflect_period_exits(group, day, period, now)
        except Exception:  # noqa: BLE001 — شعبةٌ معطوبةٌ لا تُسقط بقيّةَ المدرسة
            logger.exception("exit_reflection: تعذّر إنهاءُ خروج الشعبة [class=%s]", group.pk)
    return flipped


@transaction.atomic
def revert_derived_absence(exit_: ClassExit, by: Any = None, why: str = "") -> int:
    """عاد قبل الجرس أو أُلغي خروجُه: الغيابُ المشتقُّ منه وحدَه يرجع حاضراً.

    ويبقى رقمُ الخروج على السطر أثراً (ما لم يُحذف الخروجُ نفسُه).
    """
    session = exit_.session
    rows = list(
        StudentAttendance.objects.filter(
            student_id=exit_.student_id,
            session__class_group_id=session.class_group_id,
            session__date=session.date,
            session__start_time=session.start_time,
            source=SOURCE,
            status="absent",
            exit=exit_,
        )
    )
    if not rows:
        return 0
    audit_cell_change(
        by,
        session.school,
        exit_.student,
        session,
        before={"status": "absent", "whereabouts": rows[0].whereabouts},
        after={"status": "present", "whereabouts": ""},
        why=why or "عاد قبل نهاية الحصّة",
        exit_=exit_,
    )
    StudentAttendance.objects.filter(pk__in=[row.pk for row in rows]).update(
        status="present", whereabouts="", updated_at=timezone.now()
    )
    klass = session.class_group
    period = next(
        (p for p in periods_of(klass, session.date) if p.start == session.start_time), None
    )
    reporter = period.confirmation.confirmed_by if period and period.confirmation else None
    sync_escapes(klass, session.date, reporter or by)
    if period is not None:
        refresh_counts(klass, session.date, period)
    return len(rows)

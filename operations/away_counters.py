"""عدّاداتُ «الخارج من الفصل» للمدير والمشرف — قراءةٌ فقط، بلا أسماء (W-20261008-018، S1، D-251م وD-252م وD-279م).

كلُّ رقمٍ باسمه ووحدته ومصدره الواحد، وكلُّ لوحةٍ تقرأ من هذه الدالّة لا من حسابٍ ثانٍ:

| الحقل | الوحدة | المصدر |
|---|---|---|
| `exit_count` | مرّات | `DailyExitTally.exit_count` (بلا الامتدادات المرحَّلة) |
| `exit_seconds` | ثوانٍ | `DailyExitTally.total_seconds` + المفتوحُ مقصوصاً بنهاية دوام الطالب |
| `exit_students` / `avg_exit_seconds` | طلاب / ثوانٍ | من خرج اليوم / المتوسّط لكلّ خارج |
| `still_out` | طلاب | `ClassExit` بلا `returned_at` الآن |
| `out_with_leave` | طلاب مميّزون | عيادةٌ ونشاطٌ (`is_out_with_leave`) |
| `leave_requests` | طلاب مميّزون | `out_permit` و`left_early` اليوم |
| `absence_rows` | حصص | صفوفُ `absent` كما سُجّلت |
| `absent_students` / `ministry_absent` | طلاب | `daily_report` (حكمُ اليوم) / غيابُ الوزارة (الحصّتان الأوليان) |
| `infractions` / `serious_open` | مخالفات | يومُ **الواقعة** (`session.date`) / الدرجة ≥3 غيرُ المعالَجة |

لا يغيّر شيئاً ممّا يراه الطالبُ أو وليُّ أمره: ولا يحمل اسمَ أحد. والنطاقُ بيد المستدعي: المدير للمدرسة،
والمشرفُ وبديلُه لجناحه (`away_counters_for`).
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from typing import Any

from django.db.models import Q, Sum
from django.utils import timezone

from core.domain.attendance import IN_CUSTODY
from core.permissions import WING_BOUND_ROLES

#: «أين الطالب» التي تعني خروجاً بإذنٍ لا عيادةً ولا نشاطاً.
LEAVE_REQUEST_WHEREABOUTS = ("out_permit", "left_early")
#: مخالفةٌ جسيمة: الدرجةُ الثالثة فأعلى (`BehaviorInfraction.level`).
SERIOUS_LEVEL = 3


@dataclass(frozen=True)
class AwayCounters:
    exit_count: int = 0
    exit_seconds: int = 0
    exit_students: int = 0
    avg_exit_seconds: int = 0
    still_out: int = 0
    out_with_leave: int = 0
    leave_requests: int = 0
    absence_rows: int = 0
    absent_students: int = 0
    ministry_absent: int = 0
    infractions: int = 0
    serious_open: int = 0

    @property
    def exit_minutes(self) -> int:
        return round(self.exit_seconds / 60)

    @property
    def avg_exit_minutes(self) -> int:
        return round(self.avg_exit_seconds / 60)


def can_see_away_counters(user: Any) -> bool:
    """المدير ونوابُه للمدرسة، والمشرفُ وبديلُه لجناحه — وغيرُهم لا."""
    if getattr(user, "is_superuser", False):
        return True
    return bool(user.is_leadership() or user.get_role() in WING_BOUND_ROLES)


def _scoped(qs, student_ids, path: str = "student_id"):
    return qs if student_ids is None else qs.filter(**{f"{path}__in": student_ids})


def exit_day_totals(
    school, day: dt.date, student_ids=None, now: dt.datetime | None = None
) -> tuple[int, int, int, int]:
    """`(مرّات، ثوانٍ، طلابٌ خرجوا، ما زالوا خارجاً)` لمدرسةٍ في يوم — أختُ `exit_day_summary` لمجموعة طلاب.

    المخزَّنُ من `DailyExitTally`، والمفتوحُ إلى لحظة الاستعلام مقصوصاً بنهاية دوام الطالب (`_day_end_time`)
    فمن لم يعد لا يتضخّم مجموعُه بعد الدوام.
    """
    from operations.class_exit import _day_end_time
    from operations.models import ClassExit, DailyExitTally

    now = now or timezone.now()
    tally = _scoped(DailyExitTally.objects.filter(school=school, date=day), student_ids)
    totals = tally.aggregate(count=Sum("exit_count"), seconds=Sum("total_seconds"))
    count, seconds = totals["count"] or 0, totals["seconds"] or 0
    exited = set(tally.filter(exit_count__gt=0).values_list("student_id", flat=True))
    opened = _scoped(
        ClassExit.objects.filter(school=school, session__date=day, returned_at__isnull=True),
        student_ids,
    ).select_related("session", "session__class_group")
    still_out = 0
    for exit_ in opened:
        still_out += 1
        exited.add(exit_.student_id)
        end = timezone.make_aware(dt.datetime.combine(day, _day_end_time(exit_.session)))
        seconds += max(0, int((min(now, end) - exit_.left_at).total_seconds()))
    return count, seconds, len(exited), still_out


def away_counters(
    school, day: dt.date, *, student_ids=None, now: dt.datetime | None = None
) -> AwayCounters:
    """عدّاداتُ اليوم لمجموعة طلاب (`None` = المدرسةُ كلُّها). أعدادٌ فقط."""
    from behavior.models import BehaviorInfraction
    from operations.daily_absence import daily_report
    from operations.models import StudentAttendance

    count, seconds, exited, still_out = exit_day_totals(school, day, student_ids, now)

    marks = _scoped(StudentAttendance.objects.filter(school=school, session__date=day), student_ids)
    out_with_leave = (
        marks.filter(status="absent", whereabouts__in=IN_CUSTODY)
        .values("student_id")
        .distinct()
        .count()
    )
    leave_requests = (
        marks.filter(whereabouts__in=LEAVE_REQUEST_WHEREABOUTS)
        .values("student_id")
        .distinct()
        .count()
    )
    absence_rows = marks.filter(status="absent").count()
    report = daily_report(school, day, student_ids=student_ids)

    infractions = _scoped(
        BehaviorInfraction.objects.filter(
            Q(session__date=day) | Q(session__isnull=True, date=day), school=school
        ),
        student_ids,
    )
    return AwayCounters(
        exit_count=count,
        exit_seconds=seconds,
        exit_students=exited,
        avg_exit_seconds=round(seconds / exited) if exited else 0,
        still_out=still_out,
        out_with_leave=out_with_leave,
        leave_requests=leave_requests,
        absence_rows=absence_rows,
        absent_students=report.absent_students,
        ministry_absent=report.ministry_absent_count,
        infractions=infractions.count(),
        serious_open=infractions.filter(level__gte=SERIOUS_LEVEL, is_resolved=False).count(),
    )


def away_counters_for(
    user: Any, school, day: dt.date, now: dt.datetime | None = None
) -> AwayCounters | None:
    """عدّاداتُ المستخدم بنطاقه (المدير للمدرسة، المشرفُ وبديلُه لجناحه)؛ و`None` لمن لا يحقّ له رؤيتها."""
    if not can_see_away_counters(user):
        return None
    from wings.scope import student_scope

    scope = student_scope(user, school)
    ids = scope.student_ids() if scope.is_wing_bound else None
    return away_counters(school, day, student_ids=ids, now=now)

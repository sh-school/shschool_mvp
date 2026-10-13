"""حصصُ اليوم وخاناتُ الطلبة، ومزامنةُ مخالفات التأخّر والهروب عن الرصد — الأساسُ الذي يقرؤه الجدولُ والخروجُ والتقارير.

(حُذف كشفُ الحصص القديم — «الشبكة» — وتثبيتُه وملؤه: الجدولُ العموديّ واجهةُ الرصد الوحيدة، أمرُ المالك 2026-10-09.)

- `periods_of` حصصُ الشعبة في اليوم، و`cells_of` خانةُ كلّ طالبٍ في كلّ حصّة.
- `sync_escapes` و`_sync_rule`: ما يترتّب على الرصد من مخالفةِ التأخّر (1-01) والهروبِ من الحصّة (2-02) وإزالتها عند التصحيح.
- الحصّةُ التي لم تُرصد حتى خمس دقائق بعد نهايتها (`PERIOD_RECORDING_GRACE_MINUTES`) **فائتة**.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass

from django.utils import timezone

from operations.absence_policy import PERIOD_RECORDING_GRACE_MINUTES
from operations.day_attendance import SOURCE, enrolled_of
from operations.models import PeriodConfirmation, Session, StudentAttendance

STATES = ("present", "absent", "late")
ATTENDED = ("present", "late")

#: مصدرُ نقرة المعلّم «دخل متأخّراً» — قبل تثبيت المشرف.
TEACHER_LATE = "teacher_late"

#: «أين الطالب» التي يُعذر بها الغيابُ عن الفصل — فلا يُعدّ هروباً.
#: و«خرج دون إذن» ليس منها: هو الهروبُ نفسُه.
AWAY_WITH_LEAVE = ("clinic", "activity", "out_permit", "left_early")
WHEREABOUTS = ("", "clinic", "activity", "out_permit", "out_no_permit", "left_early")

GRACE = dt.timedelta(minutes=PERIOD_RECORDING_GRACE_MINUTES)


@dataclass
class Period:
    """خانةٌ من يوم الشعبة — حصّةٌ أو زوجُ اختيارٍ في الساعة نفسِها."""

    number: int
    start: dt.time
    end: dt.time
    sessions: list
    confirmation: PeriodConfirmation | None = None

    @property
    def subjects(self) -> str:
        names = [s.subject.name_ar for s in self.sessions if s.subject_id]
        return " / ".join(dict.fromkeys(names)) or "حصّة"

    @property
    def key(self) -> str:
        return f"{self.start:%H:%M}"

    def deadline(self, day: dt.date) -> dt.datetime:
        return timezone.make_aware(dt.datetime.combine(day, self.end)) + GRACE

    def in_window(self, day: dt.date, now: dt.datetime) -> bool:
        """نافذةُ الحصّة: من بدئها حتى خمس دقائق بعد نهايتها."""
        start = timezone.make_aware(dt.datetime.combine(day, self.start))
        return start <= now <= self.deadline(day)

    def status(self, day: dt.date, now: dt.datetime) -> str:
        """confirmed · confirmed_late · current · missed · upcoming."""
        if self.confirmation is not None:
            return "confirmed_late" if self.confirmation.confirmed_late else "confirmed"
        if self.in_window(day, now):
            return "current"
        if now > self.deadline(day):
            return "missed"
        return "upcoming"


def periods_of(class_group, day: dt.date) -> list[Period]:
    """خاناتُ الشعبة في اليوم بترتيب الساعة، ومع كلٍّ تثبيتُها إن وُجد."""
    sessions = (
        Session.objects.filter(class_group=class_group, date=day)
        .exclude(status="cancelled")
        .select_related("subject")
        .order_by("start_time")
    )
    confirmations = {
        c.start_time: c
        for c in PeriodConfirmation.objects.filter(class_group=class_group, date=day)
    }
    periods: dict[dt.time, Period] = {}
    for session in sessions:
        period = periods.get(session.start_time)
        if period is None:
            period = periods[session.start_time] = Period(
                number=len(periods) + 1,
                start=session.start_time,
                end=session.end_time,
                sessions=[],
                confirmation=confirmations.get(session.start_time),
            )
        period.sessions.append(session)
    return list(periods.values())


@dataclass(frozen=True)
class Cell:
    status: str
    whereabouts: str
    late_minutes: int | None
    exit_id: object = None

    @property
    def where_label(self) -> str:
        return dict(StudentAttendance.WHEREABOUTS).get(self.whereabouts, "")


def cells_of(class_group, day: dt.date) -> dict:
    """ما رصده المشرفُ: `{student_id: {start_time: Cell}}` — وحصّتا الزوج خانةٌ واحدة."""
    rows = (
        StudentAttendance.objects.filter(
            session__class_group=class_group, session__date=day, source=SOURCE
        )
        .values_list(
            "student_id",
            "session__start_time",
            "status",
            "whereabouts",
            "late_minutes",
            "exit_id",
        )
        .order_by("session__start_time")
    )
    cells: dict = {}
    for student_id, start_time, status, where, minutes, exit_id in rows:
        cells.setdefault(student_id, {}).setdefault(
            start_time, Cell(status, where, minutes, exit_id)
        )
    return cells


def period_end(day: dt.date, period: Period) -> dt.datetime:
    return timezone.make_aware(dt.datetime.combine(day, period.end))


def _warn_of_gates(school, absentees, day: dt.date) -> None:
    """إنذاراتُ عتبات الغياب لمن غاب في هذه الحصّة — كما كان يفعل رصدُ المعلّم.

    كان `check_absence_threshold` يُستدعى من رصد المعلّم القديم وحدَه، فلمّا انتقل
    الرصدُ إلى كشف الأجنحة لم يُنشأ تنبيهٌ ولم يُبلَّغ وليُّ أمرٍ (اكتُشف 2026-09-13).
    وهو يعدّ أيّامَ تمدرسٍ لا حصصاً، ولا يكرّر إنذاراً — فاستدعاؤه بعد كلّ حصّةٍ آمن،
    ويُنذر حين تكتمل حصصُ اليوم الغائب.
    """
    from operations.services import AttendanceService

    for student in absentees:
        AttendanceService.check_absence_threshold(student, school, on=day)


RULE_TEXT = {
    "period_tardy": "تأخّرٌ عن الحصّة بعد خمس دقائق من بدئها",
    "class_escape": "هروبٌ من الحصّة بين حضورين",
    "school_escape": "هروبٌ من المدرسة: غيابٌ بعد الحضور حتى آخر حصّةٍ في اليوم",
}


def _codes() -> dict:
    from behavior.conduct_2026 import CLASS_ESCAPE_CODE, PERIOD_TARDY_CODE, SCHOOL_ESCAPE_CODE

    return {
        "period_tardy": PERIOD_TARDY_CODE,
        "class_escape": CLASS_ESCAPE_CODE,
        "school_escape": SCHOOL_ESCAPE_CODE,
    }


def _sync_rule(school, student, rule, wanted_starts, periods_by_start, by, *, scope) -> int:
    """يجعل مخالفاتِ `rule` الآليّةَ لهذا الطالب في `scope` مطابقةً لـ`wanted_starts`.

    يُنشئ الناقصَ ويُزيل ما زال سببُه — ولا يُمسّ ما كتبه أحدٌ بيده (`auto_rule` فارغ).
    ويُرجع عددَ ما أُنشئ.
    """
    from behavior.conduct_2026 import BY_CODE
    from behavior.digest import IMMEDIATE_RULES, notify_immediately
    from behavior.models import BehaviorInfraction, ViolationCategory
    from behavior.services import BehaviorService

    existing = {
        infraction.session.start_time: infraction
        for infraction in BehaviorInfraction.objects.filter(
            student=student, session__in=scope, auto_rule=rule
        ).select_related("session")
    }
    for start, infraction in existing.items():
        if start not in wanted_starts:
            infraction.delete()

    code = _codes()[rule]
    category = ViolationCategory.objects.filter(code=code, is_active=True).first()
    if category is None:
        return 0
    made = 0
    for start in sorted(set(wanted_starts) - set(existing)):
        period = periods_by_start[start]
        infraction = BehaviorService.create_infraction(
            school=school,
            student=student,
            reporter=by,
            level=BY_CODE[code].degree,
            description=f"{RULE_TEXT[rule]} — {period.subjects} ({period.key})",
            violation_category=category,
            session=period.sessions[0],
            auto_rule=rule,
        )
        if rule in IMMEDIATE_RULES:
            # الهروبُ من المدرسة يبلغ الأسرةَ بعد التزام الرصد، لا في ملخّص العصر.
            # والتأخّرُ والهروبُ من الحصّة لا يُرسَلان من هنا: ملخّصُهما اليوميّ
            # (`behavior.digest`) يقرأ الحالةَ النهائيّةَ بعد التصحيحات.
            notify_immediately(infraction, school, by)
        made += 1
    return made


def escapes_for(track: list) -> tuple[set, set]:
    """يحكم على يوم طالبٍ: `track` = `[(start, status, whereabouts), …]` بترتيب الساعة.

    و`status` فارغٌ للحصّة غير المثبّتة. ويُرجع (خاناتُ الهروب من الحصّة، خانةُ
    الهروب من المدرسة):

    - غيابٌ بلا إذنٍ **بين حضورين** ← هروبٌ من الحصّة لكلّ حصّة (2-02).
    - غيابٌ بلا إذنٍ بعد حضورٍ **متّصلٌ حتى آخر حصّةٍ في اليوم، وكلُّها مثبّتة** ←
      هروبٌ من المدرسة (3-10)، مخالفةٌ واحدةٌ عند أوّل حصّةٍ غابها (قرارُ المدرسة).
    - وإن تخلّلته أو تلته حصّةٌ لم تُثبَّت فـ**لم يُحسم**: قد يكون عاد. فلا يُنشأ شيء.
    - ومن لم يحضر قبلها غائبٌ لا هارب، والغائبُ بإذنٍ لا هارب.
    """
    in_class: set = set()
    in_school: set = set()
    attended = False
    streak: list = []
    unknown = False
    for start, status, where in track:
        if status in ATTENDED:
            in_class.update(streak)
            streak, unknown, attended = [], False, True
        elif not status:
            if streak:
                unknown = True
        elif status == "absent" and attended and where not in AWAY_WITH_LEAVE:
            streak.append(start)
        else:
            streak, unknown = [], False
    if streak and not unknown and track and track[-1][1]:
        in_school.add(streak[0])
    return in_class, in_school


def sync_escapes(class_group, day: dt.date, by) -> int:
    """يحكم على هروب طلاب الشعبة في يومها كلِّه بعد كلّ تثبيت — ويُرجع ما أُنشئ.

    والحكمُ على اليوم لا على الحصّة: الغيابُ في الثانية لا يُعرف أهو هروبٌ من الحصّة
    أم من المدرسة حتى تُرصد الحصصُ بعدها. فيُعاد الحكمُ مع كلّ تثبيت، ويتبدّل ما
    أنشأه الرصدُ بتبدّل الحكم.
    """
    periods = periods_of(class_group, day)
    if not periods:
        return 0
    by_start = {p.start: p for p in periods}
    confirmed = {p.start for p in periods if p.confirmation is not None}
    cells = cells_of(class_group, day)
    scope = [session for p in periods for session in p.sessions]
    made = 0
    for enrollment in enrolled_of(class_group):
        own = cells.get(enrollment.student_id, {})
        track = []
        for p in periods:
            cell = own.get(p.start) if p.start in confirmed else None
            track.append((p.start, cell.status if cell else "", cell.whereabouts if cell else ""))
        in_class, in_school = escapes_for(track)
        for rule, wanted in (("class_escape", in_class), ("school_escape", in_school)):
            made += _sync_rule(
                class_group.school,
                enrollment.student,
                rule,
                wanted,
                by_start,
                by,
                scope=scope,
            )
    return made

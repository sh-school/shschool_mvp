"""كشفُ الحصص — رصدُ مشرف الجناح حصّةً حصّة، وما يترتّب على كلّ رصد.

## لِمَ الحصّةُ لا اليوم

المشرفُ يدخل الفصلَ في كلّ حصّة (قرارُ 2026-09-13): الأولى قبل نهايتها، والبقيّةَ
في بدايتها. والطالبُ يغيب في الأولى ويصل في الثالثة، ويخرج إلى العيادة في الخامسة —
فحالةٌ واحدةٌ لليوم لا تحمل ذلك. وكانت شاشةُ «الموجة الواحدة» تكتب حالةً في الحصص
السبع، فأُزيلت. وأُزيل بعدها زرُّ «انسخ الحصّةَ الأولى إلى التالية» (قرارُ
2026-09-13): كلُّ حصّةٍ دخولٌ إلى الفصل، والنسخُ يُغري بتركه.

## ما يقع عند تثبيت حصّة

- كلُّ طالبٍ لم يُلمس **حاضر** — الحصّةُ تبدأ «الكلُّ حاضر».
- **«متأخّر»**: دقائقُه تُحسب تلقائيّاً من بدء الحصّة إلى **لحظة النقرة** على
  «متأخّر» — لا لحظة التثبيت: من نُقر في 07:20 وثُبّتت حصّتُه في 07:30 تأخّر عشراً لا
  عشرين. وإن غابت لحظةُ النقرة أو خرجت عن الحصّة فلحظةُ التثبيت. وهذا في نافذة الحصّة
  (من بدئها حتى خمس دقائق بعد نهايتها)؛ وخارجَها — تصحيحُ حصّةٍ مضت — يُكتب الرقمُ
  بيد المشرف.
  وبعد **خمس دقائق** تُنشأ مخالفةُ التأخّر (1-01) نافذةً.
- **«غائب» بعد حضورٍ في حصّةٍ سابقةٍ من اليوم**: هروبٌ من الحصّة (2-02) بمادّتها،
  ما لم يكن «أين الطالب» عيادةً أو نشاطاً أو خروجاً بإذن. ومن لم يأتِ أصلاً غائبٌ
  لا هارب.
- **التصحيحُ يُصحّح**: إن عُدّلت الحالةُ فزال سببُ مخالفةٍ أنشأها الرصدُ أُزيلت، ولا
  يُمسّ ما كتبه أحدٌ بيده.

## والفائتة

الحصّةُ التي لم تُثبَّت حتى خمس دقائق بعد نهايتها (`PERIOD_RECORDING_GRACE_MINUTES`)
**فائتة**، وتبقى «لم تُرصد» — لا تُسحب إليها حالةٌ سابقة. ومحاسبةُ المشرف عليها
للنائب الإداريّ. وإن ثُبّتت بعدها صارت «ثُبّتت متأخّرة» وبقيت كذلك.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass

from django.db import transaction
from django.utils import timezone

from operations.absence_policy import PERIOD_RECORDING_GRACE_MINUTES
from operations.day_attendance import SOURCE, enrolled_of
from operations.models import PeriodConfirmation, Session, StudentAttendance
from operations.tardiness import is_period_tardy, minutes_after_start

STATES = ("present", "absent", "late")
ATTENDED = ("present", "late")

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


def focus_period(periods: list[Period], day: dt.date, now: dt.datetime) -> Period | None:
    """الحصّةُ التي تُفتح للرصد: الجارية، وإلّا أوّلُ فائتة، وإلّا أوّلُ قادمة."""
    for wanted in ("current", "missed", "upcoming"):
        for period in periods:
            if period.status(day, now) == wanted:
                return period
    return periods[-1] if periods else None


@dataclass(frozen=True)
class Cell:
    status: str
    whereabouts: str
    late_minutes: int | None

    @property
    def where_label(self) -> str:
        return dict(StudentAttendance.WHEREABOUTS).get(self.whereabouts, "")


def cells_of(class_group, day: dt.date) -> dict:
    """ما رصده المشرفُ: `{student_id: {start_time: Cell}}` — وحصّتا الزوج خانةٌ واحدة."""
    rows = (
        StudentAttendance.objects.filter(
            session__class_group=class_group, session__date=day, source=SOURCE
        )
        .values_list("student_id", "session__start_time", "status", "whereabouts", "late_minutes")
        .order_by("session__start_time")
    )
    cells: dict = {}
    for student_id, start_time, status, where, minutes in rows:
        cells.setdefault(student_id, {}).setdefault(start_time, Cell(status, where, minutes))
    return cells


def absent_yesterday(class_group, day: dt.date) -> set:
    """من غاب بلا عذرٍ في آخر يومٍ دراسيٍّ قبل هذا — والغيابُ يتكرّر."""
    last = (
        Session.objects.filter(class_group=class_group, date__lt=day)
        .exclude(status="cancelled")
        .order_by("-date")
        .values_list("date", flat=True)
        .first()
    )
    if last is None:
        return set()
    return set(
        StudentAttendance.objects.filter(
            session__class_group=class_group,
            session__date=last,
            status="absent",
            excuse_type="",
        ).values_list("student_id", flat=True)
    )


@dataclass(frozen=True)
class PeriodResult:
    period: Period
    present: int
    absent: int
    late: int
    tardy_infractions: int
    escape_infractions: int

    @property
    def says(self) -> str:
        parts = [f"الحصّة {self.period.number}: غياب {self.absent} · تأخّر {self.late}"]
        if self.tardy_infractions or self.escape_infractions:
            parts.append(f"مخالفات: تأخّر {self.tardy_infractions} · هروب {self.escape_infractions}")
        return " — ".join(parts)


def _tapped(raw, day: dt.date, period: Period, now: dt.datetime) -> dt.datetime | None:
    """لحظةُ النقرة على «متأخّر» إن صدقت: بين بدء الحصّة ولحظة التثبيت.

    تأتي من المتصفّح بساعة الخادم مصحَّحة، فلا يُوثق بها إلّا في حدودها: لحظةٌ قبل بدء
    الحصّة أو بعد التثبيت عبثٌ أو ساعةٌ مختلّة، فتُترك ويُحسب من لحظة التثبيت.
    """
    try:
        moment = dt.datetime.fromtimestamp(int(float(raw)), tz=dt.UTC)
    except (TypeError, ValueError, OverflowError, OSError):
        return None
    start = timezone.make_aware(dt.datetime.combine(day, period.start))
    return moment if start <= moment <= now else None


def _clean_minutes(raw) -> int | None:
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return None
    return value if 0 <= value <= 240 else None


@transaction.atomic
def confirm_period(
    class_group, day: dt.date, start: dt.time, marks: dict, by, now: dt.datetime | None = None
) -> PeriodResult:
    """يثبّت حصّةً: يكتب حالةَ كلّ طالبٍ في حصص خانتها، ويُنشئ مخالفاتها أو يُزيلها.

    `marks`: `{student_id: {"status", "whereabouts", "late_minutes", "tapped_at"}}` — ومن
    لم يُذكر حاضر. و`tapped_at` لحظةُ النقرة على «متأخّر» بثواني يونكس.
    """
    now = now or timezone.now()
    periods = periods_of(class_group, day)
    period = next((p for p in periods if p.start == start), None)
    if period is None:
        raise ValueError("لا حصّةَ لهذه الشعبة في هذا الوقت")
    measured_now = period.in_window(day, now)
    earlier = cells_of(class_group, day)

    tally = {"present": 0, "absent": 0, "late": 0}
    tardy = 0
    absentees = []
    for enrollment in enrolled_of(class_group):
        student = enrollment.student
        mark = marks.get(str(student.id)) or marks.get(student.id) or {}
        status = mark.get("status") if mark.get("status") in STATES else "present"
        if status == "absent":
            absentees.append(student)
        where = mark.get("whereabouts") if mark.get("whereabouts") in WHEREABOUTS else ""
        minutes = None
        if status == "late":
            tapped = _tapped(mark.get("tapped_at"), day, period, now)
            before = earlier.get(student.id, {}).get(period.start)
            if not measured_now:
                minutes = _clean_minutes(mark.get("late_minutes"))
            elif (
                tapped is None
                and before
                and before.status == "late"
                and before.late_minutes is not None
            ):
                # متأخّرٌ من تثبيتٍ سابقٍ لم يُنقر ثانيةً: دقائقُه باقية — التثبيتُ الثاني
                # بعد عشر دقائق لا يزيده عشراً.
                minutes = before.late_minutes
            else:
                minutes = minutes_after_start(period.sessions[0], timezone.localtime(tapped or now))
        tally[status] += 1

        for session in period.sessions:
            StudentAttendance.objects.update_or_create(
                session=session,
                student=student,
                defaults={
                    "school": class_group.school,
                    "status": status,
                    "source": SOURCE,
                    "marked_by": by,
                    "whereabouts": where,
                    "late_minutes": minutes,
                },
            )
        wanted = {period.start} if status == "late" and is_period_tardy(minutes) else set()
        tardy += _sync_rule(
            class_group.school,
            student,
            "period_tardy",
            wanted,
            {period.start: period},
            by,
            scope=period.sessions,
        )

    confirmation, made = PeriodConfirmation.objects.get_or_create(
        class_group=class_group,
        date=day,
        start_time=period.start,
        defaults={
            "school": class_group.school,
            "end_time": period.end,
            "confirmed_by": by,
            "first_confirmed_at": now,
            "confirmed_late": now > period.deadline(day),
            "present_count": tally["present"],
            "absent_count": tally["absent"],
            "late_count": tally["late"],
        },
    )
    if not made:
        # أوّلُ تثبيتٍ ووسمُ التأخير لا يُمسّان: التثبيتُ ثانيةً يُحدّث العدَّ ومن ثبّت.
        confirmation.confirmed_by = by
        confirmation.present_count = tally["present"]
        confirmation.absent_count = tally["absent"]
        confirmation.late_count = tally["late"]
        confirmation.save(
            update_fields=[
                "confirmed_by",
                "present_count",
                "absent_count",
                "late_count",
                "confirmed_at",
            ]
        )
    escapes = sync_escapes(class_group, day, by)
    _warn_of_gates(class_group.school, absentees, day)
    return PeriodResult(period, tally["present"], tally["absent"], tally["late"], tardy, escapes)


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
        BehaviorService.create_infraction(
            school=school,
            student=student,
            reporter=by,
            level=BY_CODE[code].degree,
            description=f"{RULE_TEXT[rule]} — {period.subjects} ({period.key})",
            violation_category=category,
            session=period.sessions[0],
            auto_rule=rule,
        )
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

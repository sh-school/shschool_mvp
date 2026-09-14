"""
operations/absence_file.py — ملفُّ غياب الطالب يوماً بيوم.

قرارُ 2026-09-14: لا آليّةَ كانت للعودة إلى يومِ غيابٍ بعينه — صفحةُ الطالب تعرض آخرَ ستّين
**حصّةً** لا أيّاماً، والعذرُ يُكتب بتاريخٍ من الذاكرة. فالملفُّ هنا يعرض العامَ الدراسيَّ
**أيّامَ الغياب وحدها**، لكلّ يومٍ حكمُه كما يحسبه عدُّ الحرمان (`absence_standing`)،
وإخطارُه، وعذرُه، ومهلتُه — ليضغط المشرفُ «اتّصلتُ» أو «عذر» على اليوم نفسه بلا كتابة تاريخ.

والعذرُ من اليوم يشمل **أيّامَ الغياب بلا عذرٍ المتّصلة** به تلقائيّاً (الجمعةُ والسبتُ
وإجازاتُ الوزارة لا تقطع الاتّصال، ويومٌ لم يُرصد يقطعه). ومهلتُه تُعدّ من عودة الطالب بعد
آخر يومٍ فيها (`operations/excuses.py`).
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass

from core.models import CalendarEvent, CustomUser, School
from operations.absence_standing import day_verdicts
from operations.bells import day_type_for
from operations.excuses import deadline_of
from operations.models import AbsenceExcuse, GuardianContact

#: الأيّامُ التي يعرضها الملفّ — ما يُحسب غياباً، وما لم يُحسم لنقص الرصد.
SHOWN = ("absent_unexcused", "absent_excused", "incomplete")

VERDICT_LABELS = {
    "absent_unexcused": "غائبٌ بلا عذر",
    "absent_excused": "غائبٌ بعذر",
    "incomplete": "رصدٌ ناقص",
}


@dataclass(frozen=True)
class AbsenceDay:
    """يومُ غيابٍ واحد بكلّ ما يحتاجه المشرفُ ليتصرّف فيه."""

    date: dt.date
    verdict: str
    absent_periods: int
    scheduled_periods: int
    #: أيّامُ الغياب بلا عذرٍ المتّصلة التي يشملها عذرٌ يُضغط من هذا اليوم.
    run_from: dt.date
    run_to: dt.date
    #: آخرُ يومٍ يقبل فيه المشرفُ العذر — ولا شيء إن لم يعد الطالبُ بعد.
    deadline: dt.date | None
    late: bool
    excuse: AbsenceExcuse | None
    waiting: AbsenceExcuse | None
    rejected: AbsenceExcuse | None
    contact: GuardianContact | None

    @property
    def label(self) -> str:
        return VERDICT_LABELS[self.verdict]

    @property
    def spans_days(self) -> bool:
        return self.run_from != self.run_to

    @property
    def may_excuse(self) -> bool:
        """يُعرض زرُّ العذر: ما دام في اليوم غيابٌ بلا عذرٍ ولم يُرسَل عذرُه للنائب."""
        return self.verdict != "absent_excused" and self.waiting is None


class _SchoolDays:
    """أيّامُ الدراسة في نافذةٍ — بإجازاتها مقروءةً مرّةً واحدة لا يوماً يوماً."""

    def __init__(self, school: School, start: dt.date, end: dt.date) -> None:
        self.breaks = list(
            CalendarEvent.objects.filter(
                academic_year__school=school,
                event_type="break",
                audience__in=("both", "students"),
                start_date__lte=end,
                end_date__gte=start,
            ).values_list("start_date", "end_date")
        )

    def __contains__(self, day: dt.date) -> bool:
        if not day_type_for(day):
            return False
        return not any(a <= day <= b for a, b in self.breaks)

    def step(self, day: dt.date, direction: int) -> dt.date:
        """اليومُ الدراسيُّ التالي (+1) أو السابق (-1) — بحدٍّ يمنع الدوران بلا نهاية."""
        for _ in range(60):
            day += dt.timedelta(days=direction)
            if day in self:
                return day
        return day


def _runs(unexcused: set[dt.date], days: _SchoolDays) -> dict[dt.date, tuple[dt.date, dt.date]]:
    """لكلّ يومِ غيابٍ بلا عذر: أوّلُ أيّام سلسلته المتّصلة وآخرُها."""
    spans: dict[dt.date, tuple[dt.date, dt.date]] = {}
    for day in sorted(unexcused):
        if day in spans:
            continue
        first = last = day
        while (before := days.step(first, -1)) in unexcused:
            first = before
        while (after := days.step(last, +1)) in unexcused:
            last = after
        cursor = first
        while cursor <= last:
            if cursor in unexcused:
                spans[cursor] = (first, last)
            cursor += dt.timedelta(days=1)
    return spans


def absence_days(
    student: CustomUser, school: School, start: dt.date, today: dt.date
) -> list[AbsenceDay]:
    """أيّامُ غياب الطالب من `start` حتى `today` — الأحدثُ أوّلاً."""
    verdicts = {
        date: (verdict, slots)
        for date, (verdict, slots) in day_verdicts(student, school, start, today).items()
        if verdict in SHOWN
    }
    if not verdicts:
        return []

    school_days = _SchoolDays(school, start, today)
    unexcused = {d for d, (v, _) in verdicts.items() if v == "absent_unexcused"}
    runs = _runs(unexcused, school_days)

    excuses = list(
        AbsenceExcuse.objects.filter(
            student=student, school=school, date_to__gte=start, date_from__lte=today
        ).order_by("-granted_at")
    )
    contacts: dict[dt.date, GuardianContact] = {}
    for contact in GuardianContact.objects.filter(
        student=student, school=school, absence_date__in=list(verdicts)
    ).order_by("contacted_at"):
        contacts[contact.absence_date] = contact

    deadlines: dict[dt.date, dt.date | None] = {}
    result = []
    for date in sorted(verdicts, reverse=True):
        verdict, slots = verdicts[date]
        run_from, run_to = runs.get(date, (date, date))
        if run_to not in deadlines:
            deadlines[run_to] = deadline_of(school, student, run_to)
        deadline = deadlines[run_to]

        def covering(status: str, on: dt.date = date) -> AbsenceExcuse | None:
            return next(
                (x for x in excuses if x.status == status and x.date_from <= on <= x.date_to),
                None,
            )

        result.append(
            AbsenceDay(
                date=date,
                verdict=verdict,
                absent_periods=len(slots["unexcused"] | slots["excused"]),
                scheduled_periods=len(slots["scheduled"]),
                run_from=run_from,
                run_to=run_to,
                deadline=deadline,
                late=deadline is not None and today > deadline,
                excuse=covering("accepted"),
                waiting=covering("pending"),
                rejected=covering("rejected"),
                contact=contacts.get(date),
            )
        )
    return result

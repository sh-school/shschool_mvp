"""توليدُ لقطات تقارير الغياب الدوريّة وجدولتُها (W-20261020-005 الخطوة 5).

الأنواعُ الأربعة ومواعيدُها (قرارُ المالك والمواصفة):

* يومي: بعد انتهاء الحصّة الثانية في يوم دراسة.
* أسبوعي: بعد آخر حصّةٍ في آخر يوم دراسةٍ من أسبوع الأحد–الخميس (الخميسُ عادةً).
* شهري: آخرُ خميسٍ من الشهر، فإن كان إجازةً فآخرُ يوم دوامٍ قبله.
* ربع سنوي: **تقريرٌ لكلّ نطاق صفوفٍ** (١–٩ / ١٠–١١ / ١٢) من بدء الفصل إلى `end_date` لحدث `midterm_exam` لذلك النطاق،
  ويُولَّد في اليوم التالي لانتهاء الاختبارات.

الإحصاءُ يُحسب **بالطلبة** من ملخّص الوزارة نفسِه (`ministry_summary`) يوماً يوماً ثم يُجمع: نسبةُ الغياب لفترةٍ =
مجموعُ (طلبةٍ غابوا الحصّتين) على مجموع (المقيَّدين) في أيام الدراسة المحسوبة. وهي أعمالُ خلفيّة (>300ms) لا تُستدعى من طلب.
اللقطةُ لا تُعدَّل: إعادةُ الحساب نسخةٌ جديدة (`AbsenceReportSnapshot.revision`).
"""

from __future__ import annotations

import calendar
import datetime as dt
from dataclasses import dataclass
from typing import Any

from django.db.models import Max

from core.academic_calendar import AcademicCalendar, _scope_for
from operations.models import AbsenceReportSnapshot, Session
from operations.school_days import is_school_day
from wings.absence_stats import StatLine, absence_stats
from wings.ministry_selectors import Counts, MinistrySummary, ministry_summary

DAILY, WEEKLY, MONTHLY, QUARTERLY = "daily", "weekly", "monthly", "quarterly"
QUARTER_SCOPES = ("g1_9", "g10_11", "g12")
#: ساعةُ احتياطٍ حين لا حصصَ مجدولةً لليوم يُقرأ منها وقتُ الانتهاء.
FALLBACK_AFTER_SECOND = dt.time(10, 30)
FALLBACK_AFTER_LAST = dt.time(14, 0)


@dataclass(frozen=True)
class ReportSpec:
    kind: str
    scope: str
    start: dt.date
    end: dt.date


def last_school_day_on_or_before(school: Any, day: dt.date) -> dt.date | None:
    """آخرُ يوم دراسةٍ حتى `day` (بحثٌ خلفيّ لا يتجاوز ٣٠ يوماً)."""
    for back in range(31):
        probe = day - dt.timedelta(days=back)
        if is_school_day(school, probe):
            return probe
    return None


def last_thursday(year: int, month: int) -> dt.date:
    last = dt.date(year, month, calendar.monthrange(year, month)[1])
    return last - dt.timedelta(days=(last.weekday() - 3) % 7)


def week_bounds(day: dt.date) -> tuple[dt.date, dt.date]:
    """الأحد–الخميس لأسبوع `day` (الأحدُ أوّلُ الأسبوع في قطر)."""
    start = day - dt.timedelta(days=(day.weekday() + 1) % 7)
    return start, start + dt.timedelta(days=4)


def _end_of_day_marks(school: Any, day: dt.date) -> tuple[dt.time, dt.time]:
    """(انتهاءُ الحصّة الثانية، انتهاءُ آخر حصّة) من حصص اليوم الفعليّة، وإلّا الاحتياط."""
    rows = list(
        Session.objects.filter(school=school, date=day)
        .exclude(status="cancelled")
        .values_list("class_group_id", "start_time")
        .annotate(end=Max("end_time"))
        .order_by("class_group_id", "start_time")
    )
    per_class: dict[Any, list[dt.time]] = {}
    for group_id, _start, end in rows:
        per_class.setdefault(group_id, []).append(end)
    seconds = [ends[1] for ends in per_class.values() if len(ends) >= 2]
    lasts = [ends[-1] for ends in per_class.values()]
    return (
        max(seconds) if seconds else FALLBACK_AFTER_SECOND,
        max(lasts) if lasts else FALLBACK_AFTER_LAST,
    )


def _is_over(day: dt.date, mark: dt.time, now: dt.datetime) -> bool:
    return now.date() > day or (now.date() == day and now.time() >= mark)


def _daily(school: Any, now: dt.datetime) -> list[ReportSpec]:
    day = last_school_day_on_or_before(school, now.date())
    if day is None:
        return []
    after_second, _ = _end_of_day_marks(school, day)
    if not _is_over(day, after_second, now):
        # لم تنتهِ الحصّةُ الثانية اليوم بعد: يومُ الدراسة السابق هو المستحقّ.
        day = last_school_day_on_or_before(school, day - dt.timedelta(days=1))
        if day is None:
            return []
    return [ReportSpec(DAILY, "", day, day)]


def _weekly(school: Any, now: dt.datetime) -> list[ReportSpec]:
    start, thursday = week_bounds(now.date())
    end = last_school_day_on_or_before(school, thursday)
    if end is None or end < start:
        return []
    if not _is_over(end, _end_of_day_marks(school, end)[1], now):
        start, thursday = week_bounds(start - dt.timedelta(days=1))
        end = last_school_day_on_or_before(school, thursday)
        if end is None or end < start:
            return []
    return [ReportSpec(WEEKLY, "", start, end)]


def _monthly(school: Any, now: dt.datetime) -> list[ReportSpec]:
    today = now.date()
    for offset in (0, 1):
        month = today.month - offset or 12
        year = today.year if today.month - offset else today.year - 1
        end = last_school_day_on_or_before(school, last_thursday(year, month))
        if end and _is_over(end, _end_of_day_marks(school, end)[1], now):
            return [ReportSpec(MONTHLY, "", dt.date(year, month, 1), end)]
    return []


def _quarterly(school: Any, now: dt.datetime) -> list[ReportSpec]:
    current = AcademicCalendar.current(school, now.date())
    if current.year is None:
        return []
    out: list[ReportSpec] = []
    events = current.year.calendar_events.filter(event_type="midterm_exam").select_related(
        "semester"
    )
    for event in events:
        if event.grade_scope not in QUARTER_SCOPES or now.date() <= event.end_date:
            continue
        start = event.semester.start_date if event.semester else current.year.start_date
        out.append(ReportSpec(QUARTERLY, event.grade_scope, start, event.end_date))
    return out


def due_specs(school: Any, now: dt.datetime) -> list[ReportSpec]:
    """كلُّ ما استحقّ توليدُه الآن وليس له لقطةٌ بعد (النسخةُ الأولى) — ثابتةُ التكرار."""
    wanted = [
        *_daily(school, now),
        *_weekly(school, now),
        *_monthly(school, now),
        *_quarterly(school, now),
    ]
    return [spec for spec in wanted if not _exists(school, spec)]


def _exists(school: Any, spec: ReportSpec) -> bool:
    return AbsenceReportSnapshot.objects.filter(
        school=school,
        kind=spec.kind,
        grade_scope=spec.scope,
        period_start=spec.start,
        period_end=spec.end,
    ).exists()


def _scoped(summary: MinistrySummary, scope: str) -> MinistrySummary:
    """ملخّصٌ بصفوف نطاقٍ واحدٍ وحدَها (للربع سنوي) والمجاميعُ تُعاد من الصفوف."""
    if not scope:
        return summary
    grades = [g for g in summary.grades if _scope_for(g.key) == scope]
    total = Counts()
    for grade in grades:
        total.add(grade.counts)
    return MinistrySummary(summary.day, grades, total, [])


def _node(line: StatLine) -> dict[str, Any]:
    return {
        "key": line.key,
        "label": line.label,
        "enrolled": line.enrolled,
        "absent": line.absent_both,
        "children": [_node(c) for c in line.children],
    }


def _merge(into: dict[str, Any], node: dict[str, Any]) -> None:
    into["enrolled"] += node["enrolled"]
    into["absent"] += node["absent"]
    kids = {c["key"]: c for c in into["children"]}
    for child in node["children"]:
        if child["key"] in kids:
            _merge(kids[child["key"]], child)
        else:
            into["children"].append(child)
            kids[child["key"]] = child


def _finish(node: dict[str, Any]) -> dict[str, Any]:
    node["rate"] = round(100 * node["absent"] / node["enrolled"], 1) if node["enrolled"] else 0.0
    node["children"] = [_finish(c) for c in node["children"]]
    return node


def _days_in(school: Any, start: dt.date, end: dt.date) -> list[dt.date]:
    return [
        start + dt.timedelta(days=i)
        for i in range((end - start).days + 1)
        if is_school_day(school, start + dt.timedelta(days=i))
    ]


def compute_payload(school: Any, spec: ReportSpec) -> tuple[dict[str, Any], int]:
    """(الإحصاء، عددُ أيام الدراسة المحسوبة): يومٌ بلا شعبةٍ لها حصّتان لا يُحسب."""
    sums: dict[str, Any] = {"school": None, "stages": {}, "wings": {}, "outside": None}
    counted = 0
    for day in _days_in(school, spec.start, spec.end):
        summary = _scoped(ministry_summary(school, day), spec.scope)
        if not any(row.has_periods for row in summary.class_rows):
            continue
        counted += 1
        stats = absence_stats(summary)
        _add(sums, "school", _node(stats.school))
        for line in stats.stages:
            _add(sums["stages"], line.key, _node(line))
        for line in stats.wings:
            _add(sums["wings"], line.key, _node(line))
        if stats.outside:
            _add(sums, "outside", _node(stats.outside))
    payload = {
        "school": _finish(sums["school"]) if sums["school"] else None,
        "stages": [_finish(n) for n in sums["stages"].values()],
        "wings": [_finish(n) for n in sums["wings"].values()],
        "outside": _finish(sums["outside"]) if sums["outside"] else None,
    }
    return payload, counted


def _add(bucket: dict[str, Any], key: str, node: dict[str, Any]) -> None:
    if bucket.get(key) is None:
        bucket[key] = node
    else:
        _merge(bucket[key], node)


def generate(school: Any, spec: ReportSpec, *, user: Any = None) -> AbsenceReportSnapshot:
    """لقطةٌ جديدةٌ بنسخةٍ تالية لنفس (النوع، النطاق، الفترة) — التوليدُ الأوّل نسخة 1، وإعادةُ الحساب أعلى."""
    payload, days = compute_payload(school, spec)
    latest = (
        AbsenceReportSnapshot.objects.filter(
            school=school,
            kind=spec.kind,
            grade_scope=spec.scope,
            period_start=spec.start,
            period_end=spec.end,
        )
        .order_by("-revision")
        .values_list("revision", flat=True)
        .first()
    )
    return AbsenceReportSnapshot.objects.create(
        school=school,
        kind=spec.kind,
        grade_scope=spec.scope,
        period_start=spec.start,
        period_end=spec.end,
        revision=(latest or 0) + 1,
        generated_by=user,
        school_days=days,
        payload=payload,
    )


def generate_due(school: Any, now: dt.datetime) -> list[AbsenceReportSnapshot]:
    """يُولّد المستحقَّ ولا يكرّر: التشغيلُ الثاني في الساعة نفسها لا يجد ما يفعله."""
    return [generate(school, spec) for spec in due_specs(school, now)]

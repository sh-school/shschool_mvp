"""النسبُ التي نُقلت من العروض إلى القُرّاء تُعرض كما كانت — حتّى عند حدّ النصف.

كانت ثلاثُ نسبٍ تُحسب `round(part / whole * 100)`: نجاحُ لوحة المدير، والخطّةُ
التشغيليّة في لوحة الإحصاءات، وحضورُ ملفّ الطالب (لمنزلةٍ واحدة). وفي الترحيل صارت
`percent`/`attendance_rate` — `part * 100 / whole` — فتغيّر المعروضُ عند الأنصاف:
23 من 40 كانت 57% فصارت 58%. والترحيلُ لا يغيّر ما يُرى، فهذه الاختباراتُ تحرس
القيمةَ القديمة على أزواجٍ يختلف فيها الحسابان.

بلا قاعدة: مصادرُ العدّ مستبدلةٌ بأرقامٍ ثابتة، فالمختبَرُ الحسابُ وحدَه.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from django.utils import timezone

from analytics import selectors as analytics_selectors
from core import views_dashboard
from core.domain.attendance import percent
from student_affairs import selectors as student_affairs_selectors


def _orm(aggregate: dict | None = None) -> MagicMock:
    """نموذجٌ بديل: `.objects.filter(...)` يُرجع `aggregate` المعطى، وكلُّ عدٍّ صفر."""
    model = MagicMock()
    chain = model.objects.filter.return_value
    chain.aggregate.return_value = aggregate if aggregate is not None else MagicMock()
    chain.count.return_value = 0
    chain.distinct.return_value.count.return_value = 0
    chain.exclude.return_value.distinct.return_value.count.return_value = 0
    return model


def test_the_pairs_below_really_differ_between_the_two_formulas():
    """وإلّا لم يحرس الاختبارُ شيئاً."""
    assert round(23 / 40 * 100) == 57 and percent(23, 40) == 58
    assert round(109 / 200 * 100) == 55 and percent(109, 200) == 54
    assert round(23 / 80 * 100, 1) == 28.7 and percent(23, 80, digits=1) == 28.8
    assert round(49 / 80 * 100, 1) == 61.3 and percent(49, 80, digits=1) == 61.2


@pytest.mark.parametrize(("passed", "total", "shown"), [(23, 40, 57), (0, 0, 0), (40, 40, 100)])
def test_director_pass_rate_is_rounded_as_before(monkeypatch, passed, total, shown):
    monkeypatch.setattr(views_dashboard, "academic_year_for_school", lambda school: "2026-2027")
    monkeypatch.setattr(views_dashboard, "session_status_counts", lambda *a: MagicMock())
    monkeypatch.setattr(
        views_dashboard,
        "_attendance_day",
        lambda school, day: ({"present": 0, "absent": 0, "late": 0}, 0),
    )
    for name in (
        "pending_absence_alerts",
        "swap_count",
        "pending_compensatory_count",
        "teacher_absence_count",
    ):
        monkeypatch.setattr(views_dashboard, name, lambda *a, **k: 0)
    monkeypatch.setattr(
        views_dashboard,
        "dashboard_selectors",
        SimpleNamespace(
            annual_result_counts=lambda school, year: {
                "total": total,
                "passed": passed,
                "failed": total - passed,
            },
            failing_student_count=lambda *a: 0,
            incomplete_setup_count=lambda *a: 0,
            behaviour_month_and_critical=lambda *a: {},
            clinic_counts_on=lambda *a: {},
            loan_count=lambda *a, **k: 0,
        ),
    )
    ctx = views_dashboard._get_director_ctx(object(), timezone.localdate())
    assert ctx["pass_pct"] == shown


@pytest.mark.parametrize(("completed", "total", "shown"), [(109, 200, 55), (0, 0, 0)])
def test_operational_plan_rate_is_rounded_as_before(monkeypatch, completed, total, shown):
    for name in (
        "StudentAttendance",
        "Session",
        "BookBorrowing",
        "BehaviorInfraction",
        "StudentEnrollment",
        "Membership",
        "ClinicVisit",
        "HealthRecord",
        "SchoolBus",
        "LibraryBook",
    ):
        monkeypatch.setattr(analytics_selectors, name, _orm())
    monkeypatch.setattr(
        analytics_selectors,
        "OperationalProcedure",
        _orm({"total": total, "completed": completed}),
    )
    kpis = analytics_selectors.school_overview_kpis(object(), "2026-2027", timezone.localdate())
    assert kpis["plan_pct"] == shown


@pytest.mark.parametrize(("present", "total", "shown"), [(23, 80, 28.7), (49, 80, 61.3), (0, 0, 0)])
def test_student_profile_attendance_rate_is_rounded_as_before(monkeypatch, present, total, shown):
    counts = {"present": present, "absent": 0, "late": 0, "excused": 0, "total": total}
    monkeypatch.setattr(
        student_affairs_selectors, "academic_year_window", lambda school: ("start", "end")
    )
    monkeypatch.setattr(student_affairs_selectors, "StudentAttendance", _orm(counts))
    infractions = MagicMock()
    infractions.aggregate.return_value = {"total": 0} | {f"level_{i}": 0 for i in range(1, 5)}
    monkeypatch.setattr(student_affairs_selectors, "student_infractions", lambda *a: infractions)
    for name in ("annual_results", "current_enrolment", "guardian_links", "recent_activities"):
        monkeypatch.setattr(student_affairs_selectors, name, lambda *a: MagicMock())
    for name in ("ClinicVisit", "HealthRecord", "BookBorrowing", "StudentTransfer"):
        monkeypatch.setattr(student_affairs_selectors, name, _orm())
    records = student_affairs_selectors.student_profile_records(object(), object(), "2026-2027")
    assert records["attendance"]["pct"] == shown

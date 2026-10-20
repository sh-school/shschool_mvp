"""
tests/test_analytics_clinic_stats.py
إحصاءُ العيادة الشهريّ يفلتر ويجمّع بالحقل الفعليّ visit_date (W-20261020-027) — كان يرمي
FieldError لأنّه يقرأ created_at وليس في ClinicVisit حقلٌ بهذا الاسم.
"""

from datetime import timedelta

import pytest
from django.utils import timezone

from analytics.services import AnalyticsService
from clinic.models import ClinicVisit


def _visit(school, student, nurse, days_ago, **kw):
    visit = ClinicVisit.objects.create(
        school=school, student=student, nurse=nurse, reason="صداع", **kw
    )
    # visit_date يُملأ تلقائياً بلحظة الإنشاء (auto_now_add)، فيُضبط بالتحديث لأشهرٍ سابقة.
    ClinicVisit.objects.filter(pk=visit.pk).update(
        visit_date=timezone.now() - timedelta(days=days_ago)
    )
    return visit


@pytest.mark.django_db
def test_clinic_stats_counts_visits_and_sent_home_per_month(school, teacher_user, nurse_user):
    _visit(school, teacher_user, nurse_user, 1, is_sent_home=True)
    _visit(school, teacher_user, nurse_user, 2, is_sent_home=False)
    _visit(school, teacher_user, nurse_user, 70, is_sent_home=True)

    rows = AnalyticsService.clinic_stats(school, months=6)

    assert sum(r["total"] for r in rows) == 3
    assert sum(r["sent_home"] for r in rows) == 2
    assert [r["month"] for r in rows] == sorted(r["month"] for r in rows)


@pytest.mark.django_db
def test_clinic_stats_excludes_visits_older_than_the_window(school, teacher_user, nurse_user):
    _visit(school, teacher_user, nurse_user, 1)
    _visit(school, teacher_user, nurse_user, 400)

    rows = AnalyticsService.clinic_stats(school, months=6)

    assert sum(r["total"] for r in rows) == 1


@pytest.mark.django_db
def test_clinic_stats_ignores_other_schools(school, teacher_user, nurse_user):
    from tests.conftest import SchoolFactory

    _visit(school, teacher_user, nurse_user, 1)

    assert AnalyticsService.clinic_stats(SchoolFactory(), months=6) == []

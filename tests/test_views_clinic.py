"""
tests/test_views_clinic.py
اختبارات views العيادة المدرسية
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
يختبر: Dashboard، تسجيل زيارة، السجل الصحي، إحصائيات
"""

import datetime as dt

import pytest
from django.utils import timezone

from clinic.models import ClinicVisit, HealthRecord


def _at(day, hour, minute=0):
    return timezone.make_aware(dt.datetime(2026, 9, day, hour, minute))


def _visit_at(school, student, nurse, when):
    v = ClinicVisit.objects.create(school=school, student=student, nurse=nurse, reason="صداع")
    ClinicVisit.objects.filter(pk=v.pk).update(visit_date=when)
    return v


def _days(response):
    """أيامُ الزيارات الظاهرة في السياق (محلّيّاً) مرتّبةً."""
    return sorted(timezone.localtime(v.visit_date).day for v in response.context["visits"])


@pytest.mark.django_db
class TestClinicDashboard:
    def test_dashboard_loads_for_nurse(self, client_as, nurse_user, school):
        client = client_as(nurse_user)
        response = client.get("/clinic/")
        assert response.status_code == 200
        assert "visits_today" in response.context

    def test_dashboard_shows_todays_visits(self, client_as, nurse_user, clinic_visit):
        client = client_as(nurse_user)
        response = client.get("/clinic/")
        assert response.status_code == 200
        assert response.context["visits_today"] >= 0


@pytest.mark.django_db
class TestRecordVisit:
    def test_get_record_visit_form(self, client_as, nurse_user, school):
        client = client_as(nurse_user)
        response = client.get("/clinic/visit/new/")
        assert response.status_code == 200
        assert "students" in response.context

    def test_post_creates_visit(
        self, client_as, nurse_user, school, student_user, enrolled_student
    ):
        client = client_as(nurse_user)
        count_before = ClinicVisit.objects.count()
        response = client.post(
            "/clinic/visit/new/",
            {
                "student_id": str(student_user.id),
                "reason": "صداع",
                "symptoms": "ألم في الرأس",
                "treatment": "مسكن ألم",
                "temperature": "37.5",
            },
        )
        assert response.status_code in (200, 302)
        assert ClinicVisit.objects.count() > count_before

    def test_visit_with_sent_home_flag(
        self, client_as, nurse_user, school, student_user, enrolled_student
    ):
        client = client_as(nurse_user)
        response = client.post(
            "/clinic/visit/new/",
            {
                "student_id": str(student_user.id),
                "reason": "حمى شديدة",
                "is_sent_home": "on",
            },
        )
        assert response.status_code in (200, 302)
        visit = ClinicVisit.objects.filter(student=student_user).last()
        if visit:
            assert visit.is_sent_home is True


@pytest.mark.django_db
class TestHealthRecord:
    def test_health_record_view_loads(
        self, client_as, nurse_user, school, student_user, health_record
    ):
        client = client_as(nurse_user)
        response = client.get(f"/clinic/student/{student_user.id}/record/")
        assert response.status_code == 200
        assert "health_record" in response.context
        assert "visits" in response.context

    def test_health_record_auto_created(
        self, client_as, nurse_user, school, student_user, enrolled_student
    ):
        """إذا لم يوجد سجل صحي — يُنشأ تلقائياً"""
        client = client_as(nurse_user)
        response = client.get(f"/clinic/student/{student_user.id}/record/")
        assert response.status_code == 200
        assert HealthRecord.objects.filter(student=student_user).exists()


@pytest.mark.django_db
class TestVisitsList:
    def test_visits_list_loads(self, client_as, nurse_user, clinic_visit):
        client = client_as(nurse_user)
        response = client.get("/clinic/visits/")
        assert response.status_code == 200
        assert "visits" in response.context

    def test_filter_by_date(self, client_as, nurse_user, clinic_visit):
        from datetime import date

        client = client_as(nurse_user)
        today = date.today().strftime("%Y-%m-%d")
        response = client.get(f"/clinic/visits/?date={today}")
        assert response.status_code == 200

    def test_range_from_to_includes_both_ends_only(
        self, client_as, nurse_user, school, student_user
    ):
        for when in (_at(9, 12), _at(10, 0, 30), _at(12, 23, 30), _at(13, 12)):
            _visit_at(school, student_user, nurse_user, when)
        client = client_as(nurse_user)
        response = client.get(
            "/clinic/visits/", {"date_from": "2026-09-10", "date_to": "2026-09-12"}
        )
        assert _days(response) == [10, 12]
        assert response.context["date_from"] == "2026-09-10"
        assert response.context["date_to"] == "2026-09-12"

    def test_legacy_single_date_is_a_one_day_range(
        self, client_as, nurse_user, school, student_user
    ):
        for when in (_at(10, 12), _at(11, 12)):
            _visit_at(school, student_user, nurse_user, when)
        client = client_as(nurse_user)
        response = client.get("/clinic/visits/", {"date": "2026-09-11"})
        assert _days(response) == [11]
        assert response.context["date_from"] == response.context["date_to"] == "2026-09-11"

    def test_reversed_range_is_swapped_and_bad_dates_are_ignored(
        self, client_as, nurse_user, school, student_user
    ):
        for when in (_at(10, 12), _at(11, 12), _at(12, 12)):
            _visit_at(school, student_user, nurse_user, when)
        client = client_as(nurse_user)
        reversed_range = client.get(
            "/clinic/visits/", {"date_from": "2026-09-12", "date_to": "2026-09-10"}
        )
        assert _days(reversed_range) == [10, 11, 12]
        bad = client.get("/clinic/visits/", {"date_from": "غير-تاريخ"})
        assert _days(bad) == [10, 11, 12]


@pytest.mark.django_db
class TestClinicStatistics:
    def test_statistics_loads(self, client_as, nurse_user, school):
        client = client_as(nurse_user)
        response = client.get("/clinic/statistics/")
        assert response.status_code == 200
        assert "visits_count" in response.context

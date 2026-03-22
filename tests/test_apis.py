"""
tests/test_apis.py
اختبارات Analytics APIs (Chart.js)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
يختبر: كل API يُعيد JSON صحيح بالبنية المطلوبة
"""

import json

import pytest

# ── مساعد ────────────────────────────────────────────────────


def get_json(client, url):
    response = client.get(url)
    assert response.status_code == 200, f"Expected 200 on {url}, got {response.status_code}"
    assert response["Content-Type"] == "application/json"
    return json.loads(response.content)


def assert_chart_structure(data):
    """كل API يُعيد labels + datasets"""
    assert "labels" in data, "Missing 'labels' in response"
    assert "datasets" in data, "Missing 'datasets' in response"
    assert isinstance(data["labels"], list)
    assert isinstance(data["datasets"], list)
    assert len(data["datasets"]) >= 1


# ══════════════════════════════════════════════
#  Attendance Trend API
# ══════════════════════════════════════════════


@pytest.mark.django_db
class TestAttendanceTrendAPI:
    def test_returns_chart_structure(self, client_as, principal_user, school):
        client = client_as(principal_user)
        data = get_json(client, "/analytics/api/attendance-trend/")
        assert_chart_structure(data)

    def test_with_custom_days(self, client_as, principal_user, school):
        client = client_as(principal_user)
        data = get_json(client, "/analytics/api/attendance-trend/?days=7")
        assert_chart_structure(data)

    def test_teacher_gets_403(self, client_as, teacher_user):
        client = client_as(teacher_user)
        response = client.get("/analytics/api/attendance-trend/")
        assert response.status_code == 403


# ══════════════════════════════════════════════
#  Grades Distribution API
# ══════════════════════════════════════════════


@pytest.mark.django_db
class TestGradesDistributionAPI:
    def test_returns_chart_structure(self, client_as, principal_user, school):
        client = client_as(principal_user)
        data = get_json(client, "/analytics/api/grades-distribution/")
        assert_chart_structure(data)

    def test_labels_are_grade_ranges(self, client_as, principal_user, school):
        client = client_as(principal_user)
        data = get_json(client, "/analytics/api/grades-distribution/")
        assert "90-100" in data["labels"]
        assert "أقل من 50" in data["labels"]

    def test_colors_match_labels_count(self, client_as, principal_user, school):
        client = client_as(principal_user)
        data = get_json(client, "/analytics/api/grades-distribution/")
        colors = data["datasets"][0]["backgroundColor"]
        assert len(colors) == len(data["labels"])


# ══════════════════════════════════════════════
#  Plan Progress API
# ══════════════════════════════════════════════


@pytest.mark.django_db
class TestPlanProgressAPI:
    def test_returns_chart_structure(self, client_as, principal_user, school):
        client = client_as(principal_user)
        data = get_json(client, "/analytics/api/plan-progress/")
        assert_chart_structure(data)

    def test_has_complete_and_pending_datasets(self, client_as, principal_user, school):
        client = client_as(principal_user)
        data = get_json(client, "/analytics/api/plan-progress/")
        labels = [ds["label"] for ds in data["datasets"]]
        assert "مكتمل" in labels
        assert "قيد التنفيذ" in labels


# ══════════════════════════════════════════════
#  Behavior Trend API
# ══════════════════════════════════════════════


@pytest.mark.django_db
class TestBehaviorTrendAPI:
    def test_returns_chart_structure(self, client_as, principal_user, school):
        client = client_as(principal_user)
        data = get_json(client, "/analytics/api/behavior-trend/")
        assert_chart_structure(data)

    def test_has_4_level_datasets(self, client_as, principal_user, school):
        """يجب أن يكون للدرجات الأربع dataset منفصل"""
        client = client_as(principal_user)
        data = get_json(client, "/analytics/api/behavior-trend/")
        assert len(data["datasets"]) == 4

    def test_level_labels_in_arabic(self, client_as, principal_user, school):
        client = client_as(principal_user)
        data = get_json(client, "/analytics/api/behavior-trend/")
        all_labels = [ds["label"] for ds in data["datasets"]]
        assert any("بسيطة" in l for l in all_labels)
        assert any("جسيمة" in l for l in all_labels)

    def test_teacher_gets_403(self, client_as, teacher_user):
        client = client_as(teacher_user)
        response = client.get("/analytics/api/behavior-trend/")
        assert response.status_code == 403


# ══════════════════════════════════════════════
#  Clinic Stats API
# ══════════════════════════════════════════════


@pytest.mark.django_db
class TestClinicStatsAPI:
    def test_returns_chart_structure(self, client_as, principal_user, school):
        client = client_as(principal_user)
        data = get_json(client, "/analytics/api/clinic-stats/")
        assert_chart_structure(data)

    def test_has_visits_and_sent_home_datasets(self, client_as, principal_user, school):
        client = client_as(principal_user)
        data = get_json(client, "/analytics/api/clinic-stats/")
        labels = [ds["label"] for ds in data["datasets"]]
        assert any("زيارات" in l for l in labels)
        assert any("منزل" in l or "أُرسل" in l for l in labels)


# ══════════════════════════════════════════════
#  Class Comparison + Subject Comparison
# ══════════════════════════════════════════════


@pytest.mark.django_db
class TestComparisonAPIs:
    def test_class_comparison_structure(self, client_as, principal_user, school):
        client = client_as(principal_user)
        data = get_json(client, "/analytics/api/class-comparison/")
        assert_chart_structure(data)

    def test_subject_comparison_structure(self, client_as, principal_user, school):
        client = client_as(principal_user)
        data = get_json(client, "/analytics/api/subject-comparison/")
        assert_chart_structure(data)
        # يجب أن يحتوي على dataset واحد للمتوسط وآخر للرسوب
        assert len(data["datasets"]) == 2

    def test_failing_by_class_structure(self, client_as, principal_user, school):
        client = client_as(principal_user)
        data = get_json(client, "/analytics/api/failing-by-class/")
        assert_chart_structure(data)

"""Regression tests for URL-redirection security guards."""

import uuid
from urllib.parse import parse_qs, urlsplit

import pytest
from django.test import RequestFactory
from django.urls import reverse

from behavior.views import _behavior_report_redirect
from operations.views_schedule import _safe_schedule_settings_redirect
from quality.models import QualityCommitteeMember
from quality.views_committee import _committee_redirect
from quality.views_executor import _executor_mapping_redirect


@pytest.fixture
def rf(settings):
    settings.ALLOWED_HOSTS = ["testserver", "localhost"]
    return RequestFactory()


def assert_relative_local(response):
    parsed = urlsplit(response["Location"])
    assert parsed.scheme == ""
    assert parsed.netloc == ""


def redirect_query(response):
    return parse_qs(
        urlsplit(response["Location"]).query,
        keep_blank_values=True,
    )


@pytest.mark.parametrize(
    "committee_type",
    [
        QualityCommitteeMember.REVIEW,
        QualityCommitteeMember.EXECUTOR,
    ],
)
def test_committee_redirect_encodes_year(
    rf,
    committee_type,
):
    request = rf.post("/quality/committee/add/")
    year = "2025-2026&next=https://evil.example/phish"

    response = _committee_redirect(
        request,
        committee_type,
        year,
    )

    assert_relative_local(response)
    assert redirect_query(response) == {"year": [year]}


def test_executor_redirect_encodes_year(rf):
    request = rf.post("/quality/executor-mapping/save/")
    year = "2025-2026&next=https://evil.example/phish"

    response = _executor_mapping_redirect(
        request,
        year,
    )

    assert_relative_local(response)
    assert response["Location"].startswith("/quality/executor-mapping/")
    assert redirect_query(response) == {"year": [year]}


def test_behavior_report_redirect_encodes_query_values(rf):
    student_id = uuid.uuid4()
    year = "2025-2026&next=https://evil.example/year"
    period = "full&next=https://evil.example/period"

    request = rf.post(f"/behavior/report/student/{student_id}/")

    response = _behavior_report_redirect(
        request,
        student_id,
        year,
        period,
    )

    assert_relative_local(response)
    assert response["Location"].startswith(f"/behavior/report/student/{student_id}/")
    assert redirect_query(response) == {
        "year": [year],
        "period": [period],
    }


@pytest.mark.parametrize(
    "referer",
    [
        "https://evil.example/phish",
        "//evil.example/phish",
        "javascript:alert(1)",
    ],
)
def test_schedule_external_referer_uses_year_fallback(
    rf,
    referer,
):
    request = rf.post(
        "/operations/schedule-settings/exemption/add/",
        HTTP_REFERER=referer,
    )

    response = _safe_schedule_settings_redirect(
        request,
        "2025-2026",
    )

    assert_relative_local(response)
    assert urlsplit(response["Location"]).path == reverse("schedule_settings")
    assert redirect_query(response) == {"year": ["2025-2026"]}


def test_schedule_same_host_referer_is_preserved(rf):
    referer = "http://testserver/teacher/schedule-settings/" "?year=2025-2026"

    request = rf.post(
        "/operations/schedule-settings/exemption/add/",
        HTTP_REFERER=referer,
    )

    response = _safe_schedule_settings_redirect(
        request,
        "ignored-year",
    )

    assert response["Location"] == referer


def test_schedule_missing_referer_preserves_year(rf):
    request = rf.post("/operations/schedule-settings/exemption/add/")

    response = _safe_schedule_settings_redirect(
        request,
        "2025-2026",
    )

    assert_relative_local(response)
    assert urlsplit(response["Location"]).path == reverse("schedule_settings")
    assert redirect_query(response) == {"year": ["2025-2026"]}


def test_schedule_fallback_year_is_encoded(rf):
    request = rf.post("/operations/schedule-settings/exemption/add/")
    year = "2025-2026&next=https://evil.example/phish"

    response = _safe_schedule_settings_redirect(
        request,
        year,
    )

    assert_relative_local(response)
    assert redirect_query(response) == {"year": [year]}


def test_schedule_without_fallback_year_uses_named_route(rf):
    request = rf.post("/operations/schedule-settings/toggle/")

    response = _safe_schedule_settings_redirect(request)

    assert_relative_local(response)
    assert response["Location"] == reverse("schedule_settings")

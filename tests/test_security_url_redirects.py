"""Regression tests for URL-redirection security guards."""

import uuid
from urllib.parse import urlsplit

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


@pytest.mark.parametrize(
    "committee_type",
    [
        QualityCommitteeMember.REVIEW,
        QualityCommitteeMember.EXECUTOR,
    ],
)
def test_committee_redirect_stays_local(
    rf,
    committee_type,
):
    request = rf.post("/quality/committee/add/")

    response = _committee_redirect(
        request,
        committee_type,
        "https://evil.example/phish",
    )

    assert_relative_local(response)


def test_executor_redirect_stays_local(rf):
    request = rf.post("/quality/executor-mapping/save/")

    response = _executor_mapping_redirect(
        request,
        "https://evil.example/phish",
    )

    assert_relative_local(response)

    assert response["Location"].startswith("/quality/executor-mapping/")


def test_behavior_report_redirect_stays_local(rf):
    student_id = uuid.uuid4()

    request = rf.post(f"/behavior/report/student/{student_id}/")

    response = _behavior_report_redirect(
        request,
        student_id,
        "2025-2026",
        "https://evil.example/phish",
    )

    assert_relative_local(response)

    assert response["Location"].startswith(f"/behavior/report/student/{student_id}/")


@pytest.mark.parametrize(
    "referer",
    [
        "https://evil.example/phish",
        "//evil.example/phish",
        "javascript:alert(1)",
    ],
)
def test_schedule_external_referer_falls_back(
    rf,
    referer,
):
    request = rf.post(
        "/operations/schedule-settings/exemption/add/",
        HTTP_REFERER=referer,
    )

    response = _safe_schedule_settings_redirect(request)

    assert_relative_local(response)

    assert response["Location"] == reverse("schedule_settings")


def test_schedule_same_host_referer_is_preserved(rf):
    referer = "http://testserver/operations/schedule-settings/" "?year=2025-2026"

    request = rf.post(
        "/operations/schedule-settings/exemption/add/",
        HTTP_REFERER=referer,
    )

    response = _safe_schedule_settings_redirect(request)

    assert response["Location"] == referer


def test_schedule_missing_referer_falls_back(rf):
    request = rf.post("/operations/schedule-settings/exemption/add/")

    response = _safe_schedule_settings_redirect(request)

    assert_relative_local(response)

    assert response["Location"] == reverse("schedule_settings")

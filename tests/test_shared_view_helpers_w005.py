"""الدوالّ المشتركة في العروض: resolve_year وفحص ملكية المعلّم (W-20261105-005)."""

from types import SimpleNamespace
from unittest.mock import patch

from django.test import RequestFactory

from assessments.views import _deny_non_owner
from core.academic_calendar import resolve_year


def test_resolve_year_prefers_query_param():
    request = RequestFactory().get("/", {"year": "2030-2031"})
    assert resolve_year(request) == "2030-2031"


def test_resolve_year_falls_back_to_current_year():
    request = RequestFactory().get("/", {"year": ""})
    with patch("core.academic_calendar.academic_year_for", return_value="2026-2027"):
        assert resolve_year(request) == "2026-2027"


def _request(user):
    return SimpleNamespace(user=user)


def test_deny_non_owner_allows_admin_and_owner():
    teacher = object()
    setup = SimpleNamespace(teacher=teacher)
    admin = SimpleNamespace(is_admin=lambda: True)
    owner = SimpleNamespace(is_admin=lambda: False)
    setup_owned = SimpleNamespace(teacher=owner)
    assert _deny_non_owner(_request(admin), setup) is None
    assert _deny_non_owner(_request(owner), setup_owned) is None


def test_deny_non_owner_returns_403_for_other_teacher():
    other = SimpleNamespace(is_admin=lambda: False)
    response = _deny_non_owner(_request(other), SimpleNamespace(teacher=object()))
    assert response.status_code == 403

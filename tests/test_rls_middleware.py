"""
tests/test_rls_middleware.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━
اختبارات PostgreSQL Row-Level Security Middleware.
"""

import pytest
from django.test import RequestFactory

from core.middleware_rls import RLSMiddleware

pytestmark = pytest.mark.django_db


class TestRLSMiddleware:
    """اختبارات RLS Middleware."""

    def test_middleware_initializes(self):
        """الـ middleware يُنشأ بنجاح."""
        middleware = RLSMiddleware(get_response=lambda r: None)
        assert middleware is not None

    def test_get_school_id_for_authenticated_user(self, principal_user, school):
        """يستخرج school_id للمستخدم المُعتمَد."""
        middleware = RLSMiddleware(get_response=lambda r: None)
        factory = RequestFactory()
        request = factory.get("/dashboard/")
        request.user = principal_user

        school_id = middleware._get_school_id(request)
        assert school_id == str(school.pk)

    def test_get_school_id_returns_none_for_anonymous(self):
        """يرجع None للمستخدم المجهول."""
        from django.contrib.auth.models import AnonymousUser

        middleware = RLSMiddleware(get_response=lambda r: None)
        factory = RequestFactory()
        request = factory.get("/auth/login/")
        request.user = AnonymousUser()

        school_id = middleware._get_school_id(request)
        assert school_id is None

    def test_middleware_does_not_crash_on_missing_user(self):
        """الـ middleware لا ينهار بدون user."""
        middleware = RLSMiddleware(get_response=lambda r: None)
        factory = RequestFactory()
        request = factory.get("/health/")
        # لا user على الطلب

        school_id = middleware._get_school_id(request)
        assert school_id is None

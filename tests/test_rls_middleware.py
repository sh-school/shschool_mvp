"""
tests/test_rls_middleware.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━
اختبارات PostgreSQL Row-Level Security Middleware.

العقد الجديد (0033): _context(request) يُعيد
  - '*'           للـ superuser
  - str(school.pk) للمستخدم العادي
  - ''             لغير المُعتمَد / بلا مدرسة (fail-closed)
"""

import pytest
from django.contrib.auth.models import AnonymousUser
from django.test import RequestFactory

from core.middleware_rls import RLSMiddleware

pytestmark = pytest.mark.django_db


class TestRLSMiddleware:
    """اختبارات RLS Middleware."""

    def test_middleware_initializes(self):
        """الـ middleware يُنشأ بنجاح."""
        middleware = RLSMiddleware(get_response=lambda r: None)
        assert middleware is not None

    def test_context_for_normal_user_is_school_pk(self, principal_user, school):
        """المستخدم العادي (غير superuser) ⇒ السياق = معرّف مدرسته."""
        principal_user.is_superuser = False
        middleware = RLSMiddleware(get_response=lambda r: None)
        request = RequestFactory().get("/dashboard/")
        request.user = principal_user

        assert middleware._context(request) == str(school.pk)

    def test_context_for_superuser_is_wildcard(self, principal_user):
        """الـ superuser ⇒ السياق = '*' (يرى كل المدارس)."""
        principal_user.is_superuser = True
        middleware = RLSMiddleware(get_response=lambda r: None)
        request = RequestFactory().get("/dashboard/")
        request.user = principal_user

        assert middleware._context(request) == "*"

    def test_context_empty_for_anonymous(self):
        """المستخدم المجهول ⇒ '' (fail-closed)."""
        middleware = RLSMiddleware(get_response=lambda r: None)
        request = RequestFactory().get("/auth/login/")
        request.user = AnonymousUser()

        assert middleware._context(request) == ""

    def test_does_not_crash_on_missing_user(self):
        """الـ middleware لا ينهار بدون user ⇒ ''."""
        middleware = RLSMiddleware(get_response=lambda r: None)
        request = RequestFactory().get("/health/")

        assert middleware._context(request) == ""

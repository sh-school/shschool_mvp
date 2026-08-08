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
from django.db import connection
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


class TestRLSSchema:
    """Guard the database-level tenant isolation contract."""

    EXCLUDED_BOOTSTRAP_TABLES = {
        "core_membership",
        "core_role",
    }

    def test_every_school_scoped_table_has_canonical_rls(self):
        """Every non-bootstrap school_id table must have exactly one RLS policy."""
        if connection.vendor != "postgresql":
            pytest.skip("PostgreSQL-specific RLS schema contract")

        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT
                    c.relname AS table_name,
                    c.relrowsecurity AS rls_enabled,
                    COUNT(p.policyname) AS policy_count,
                    COUNT(p.policyname) FILTER (
                        WHERE p.policyname = 'school_isolation'
                    ) AS canonical_policy_count,
                    COUNT(p.policyname) FILTER (
                        WHERE p.policyname = 'school_isolation'
                          AND p.qual IS NOT NULL
                          AND p.with_check IS NOT NULL
                    ) AS guarded_policy_count
                FROM pg_class AS c
                JOIN pg_namespace AS n
                  ON n.oid = c.relnamespace
                JOIN information_schema.columns AS columns
                  ON columns.table_schema = n.nspname
                 AND columns.table_name = c.relname
                 AND columns.column_name = 'school_id'
                LEFT JOIN pg_policies AS p
                  ON p.schemaname = n.nspname
                 AND p.tablename = c.relname
                WHERE n.nspname = 'public'
                  AND c.relkind = 'r'
                GROUP BY
                    c.relname,
                    c.relrowsecurity
                ORDER BY c.relname
                """
            )
            rows = cursor.fetchall()

        discovered = {row[0] for row in rows}

        assert self.EXCLUDED_BOOTSTRAP_TABLES <= discovered

        rls_disabled = {table_name for table_name, rls_enabled, *_ in rows if not rls_enabled}

        assert rls_disabled == self.EXCLUDED_BOOTSTRAP_TABLES

        invalid_policies = [
            (
                table_name,
                policy_count,
                canonical_policy_count,
                guarded_policy_count,
            )
            for (
                table_name,
                rls_enabled,
                policy_count,
                canonical_policy_count,
                guarded_policy_count,
            ) in rows
            if table_name not in self.EXCLUDED_BOOTSTRAP_TABLES
            and (
                not rls_enabled
                or policy_count != 1
                or canonical_policy_count != 1
                or guarded_policy_count != 1
            )
        ]

        assert invalid_policies == []

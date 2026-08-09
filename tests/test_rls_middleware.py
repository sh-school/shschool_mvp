"""
tests/test_rls_middleware.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━
اختبارات PostgreSQL Row-Level Security Middleware.

العقد الحالي (0037): _context(request) يُعيد
  - str(school.pk) لكل مستخدم مُعتمَد له عضوية — بما فيهم الـ superuser
  - ''             لغير المُعتمَد / بلا عضوية (fail-closed)

أُزيل التجاوز '*' لأنه كان متغيّر جلسة يستطيع أي دور ضبطه بلا صلاحية.
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

    def test_context_for_superuser_is_own_school(self, principal_user, school):
        """[SEC-05] الـ superuser يُحلّ عبر عضويته — لا تجاوز '*'."""
        principal_user.is_superuser = True
        middleware = RLSMiddleware(get_response=lambda r: None)
        request = RequestFactory().get("/dashboard/")
        request.user = principal_user

        context = middleware._context(request)

        assert context == str(school.pk)
        assert context != "*"

    def test_context_never_returns_wildcard_without_membership(self, principal_user):
        """[SEC-05] superuser بلا عضوية ⇒ '' (fail-closed) لا '*'."""
        principal_user.is_superuser = True
        principal_user.memberships.update(is_active=False)
        # العضوية مُخزَّنة مؤقتاً على النسخة (_active_membership) — يجب إبطالها.
        principal_user.invalidate_active_membership()
        middleware = RLSMiddleware(get_response=lambda r: None)
        request = RequestFactory().get("/dashboard/")
        request.user = principal_user

        assert middleware._context(request) == ""

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

    def test_no_policy_references_the_wildcard_bypass(self):
        """[SEC-05] لا سياسة تستدعي app_rls_bypass — التجاوز أُزيل (0037)."""
        if connection.vendor != "postgresql":
            pytest.skip("PostgreSQL-specific RLS schema contract")

        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT tablename
                FROM pg_policies
                WHERE schemaname = 'public'
                  AND policyname = 'school_isolation'
                  AND (
                      coalesce(qual, '') LIKE '%%app_rls_bypass%%'
                      OR coalesce(with_check, '') LIKE '%%app_rls_bypass%%'
                  )
                ORDER BY tablename
                """
            )
            tables_with_bypass = [row[0] for row in cursor.fetchall()]

        assert tables_with_bypass == []

    def test_wildcard_context_grants_no_access(self):
        """[SEC-05] app_rls_bypass() ثابتة false مهما كان السياق."""
        if connection.vendor != "postgresql":
            pytest.skip("PostgreSQL-specific RLS schema contract")

        with connection.cursor() as cursor:
            cursor.execute("SELECT set_config('app.current_school_id', '*', true)")
            cursor.execute("SELECT app_rls_bypass(), app_rls_school()")
            bypass, school_id = cursor.fetchone()
            cursor.execute("SELECT set_config('app.current_school_id', '', true)")

        assert bypass is False
        assert school_id is None

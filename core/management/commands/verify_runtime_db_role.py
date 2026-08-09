"""Fail-closed verification for the production runtime database role."""

from django.core.management.base import BaseCommand, CommandError
from django.db import connection

EXPECTED_ROLE = "shschool_app"
CRITICAL_RLS_TABLE = "operations_session"
CRITICAL_RLS_RELATION = f"public.{CRITICAL_RLS_TABLE}"
CRITICAL_POLICY = "school_isolation"


class Command(BaseCommand):
    help = "Verify that runtime DB access uses the non-superuser RLS role."

    def handle(self, *args, **options):
        if connection.vendor != "postgresql":
            raise CommandError("Production worker runtime requires PostgreSQL.")

        with connection.cursor() as cursor:
            cursor.execute("SELECT current_user")
            role = cursor.fetchone()[0]

            cursor.execute(
                """
                SELECT
                    rolsuper,
                    rolbypassrls,
                    rolcanlogin,
                    rolinherit
                FROM pg_roles
                WHERE rolname = current_user
                """
            )
            role_flags = cursor.fetchone()

            cursor.execute("SELECT current_setting(" "'app.current_school_id', true)")
            context_row = cursor.fetchone()
            rls_context = context_row[0] if context_row else None

            cursor.execute(
                """
                SELECT c.relrowsecurity
                FROM pg_class AS c
                WHERE c.oid = %s::regclass
                """,
                [CRITICAL_RLS_RELATION],
            )
            table_row = cursor.fetchone()

            cursor.execute(
                """
                SELECT COUNT(*)
                FROM pg_policies
                WHERE schemaname = 'public'
                  AND tablename = %s
                  AND policyname = %s
                """,
                [
                    CRITICAL_RLS_TABLE,
                    CRITICAL_POLICY,
                ],
            )
            policy_count = cursor.fetchone()[0]

            cursor.execute(
                """
                SELECT COUNT(*)
                FROM pg_class AS c
                JOIN pg_namespace AS n
                  ON n.oid = c.relnamespace
                WHERE n.nspname = 'public'
                  AND c.relkind IN ('r', 'p')
                  AND c.relowner = (
                      SELECT oid
                      FROM pg_roles
                      WHERE rolname = current_user
                  )
                """
            )
            owned_public_tables = cursor.fetchone()[0]

        if role_flags is None:
            raise CommandError(f"Runtime DB role metadata missing for {role!r}.")

        (
            superuser,
            bypass_rls,
            can_login,
            inherit,
        ) = role_flags

        if role != EXPECTED_ROLE:
            raise CommandError(
                "Unsafe runtime DB role: " f"expected {EXPECTED_ROLE!r}, got {role!r}."
            )

        if superuser:
            raise CommandError("Unsafe runtime DB role: superuser=true.")

        if bypass_rls:
            raise CommandError("Unsafe runtime DB role: bypassrls=true.")

        if not can_login:
            raise CommandError("Runtime DB role cannot login.")

        if inherit:
            raise CommandError("Unsafe runtime DB role: inherit=true.")

        if owned_public_tables:
            raise CommandError(
                "Unsafe runtime DB role owns public tables: " f"{owned_public_tables}."
            )

        if not table_row or not table_row[0]:
            raise CommandError("RLS is not enabled on critical table " f"{CRITICAL_RLS_TABLE!r}.")

        if policy_count != 1:
            raise CommandError(
                f"Expected exactly one {CRITICAL_POLICY!r} "
                f"policy on {CRITICAL_RLS_TABLE!r}; "
                f"found {policy_count}."
            )

        if rls_context not in (None, ""):
            raise CommandError("Worker startup inherited a non-empty " "tenant RLS context.")

        self.stdout.write(
            self.style.SUCCESS(
                "runtime DB role verified: "
                "role=shschool_app "
                "super=false bypassrls=false "
                "inherit=false owned_tables=0 "
                "rls=enabled "
                "policy=school_isolation "
                "context=unset"
            )
        )

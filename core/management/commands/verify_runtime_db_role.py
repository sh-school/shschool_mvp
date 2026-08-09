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
                    rolinherit,
                    rolcreatedb,
                    rolcreaterole
                FROM pg_roles
                WHERE rolname = current_user
                """
            )
            role_flags = cursor.fetchone()

            # NOINHERIT blocks automatic inheritance but never blocks SET ROLE,
            # so any membership in a privileged role is still an escalation path.
            # pg_has_role resolves the membership graph transitively — a direct
            # pg_auth_members count would miss role -> intermediate -> privileged.
            cursor.execute(
                """
                SELECT COUNT(*)
                FROM pg_roles AS r
                WHERE r.rolname <> current_user
                  AND pg_has_role(current_user, r.oid, 'MEMBER')
                """
            )
            role_memberships = cursor.fetchone()[0]

            # CREATE on schema public would let the runtime role create tables it
            # owns, and an owner bypasses RLS on its own tables.
            cursor.execute("SELECT has_schema_privilege(current_user, 'public', 'CREATE')")
            can_create_in_public = cursor.fetchone()[0]

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
            create_db,
            create_role,
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

        if create_db:
            raise CommandError("Unsafe runtime DB role: createdb=true.")

        if create_role:
            raise CommandError("Unsafe runtime DB role: createrole=true.")

        if role_memberships:
            raise CommandError(
                "Unsafe runtime DB role holds role memberships: "
                f"{role_memberships} (SET ROLE escalation path)."
            )

        if can_create_in_public:
            raise CommandError(
                "Unsafe runtime DB role has CREATE on schema public "
                "(could own tables and bypass RLS)."
            )

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
                "createdb=false createrole=false "
                "memberships=0 schema_create=false "
                "rls=enabled "
                "policy=school_isolation "
                "context=unset"
            )
        )

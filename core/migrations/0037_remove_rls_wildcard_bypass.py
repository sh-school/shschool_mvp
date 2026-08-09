"""Remove the client-settable RLS wildcard bypass.

`app_rls_bypass()` (migrations 0033 and 0036) returned true whenever the session
variable `app.current_school_id` equalled '*'.  Placeholder GUCs in a
user-defined namespace can be set by any PostgreSQL role without privilege, so a
single `SET app.current_school_id = '*'` — reachable through statement chaining
in a SQL injection — disabled tenant isolation on every school-scoped table at
once.  That is precisely the attack RLS exists to backstop, so the bypass
removed the defence-in-depth value of the whole design.

Two independent changes close it:

1. Every `school_isolation` predicate drops the `app_rls_bypass()` call.
2. `app_rls_bypass()` is redefined to a constant false, so any policy that still
   references it (older environments, partially applied history) cannot bypass
   either.

The table owner keeps its implicit bypass: the tables use ENABLE ROW LEVEL
SECURITY, not FORCE, so migrations and owner-role management commands are
unaffected.  Only the runtime application role `shschool_app` is constrained.

Superuser cross-school visibility is withdrawn deliberately; a Django superuser
is now scoped through their Membership like every other user.  See
`core/middleware_rls.py`.

core_membership and core_role stay excluded for the same reason as 0036: they
resolve a user's school before any tenant context exists.
"""

from django.db import migrations

# ══════════════════════════════════════════════════════════════════
# Forward — bypass disabled, predicates rewritten without it
# ══════════════════════════════════════════════════════════════════

DISABLE_BYPASS_SQL = """
CREATE OR REPLACE FUNCTION app_rls_bypass() RETURNS boolean
    LANGUAGE sql STABLE AS $$
    SELECT false;
$$;
"""

RECONCILE_SQL = """
DO $$
DECLARE
    target record;
    predicate text;
BEGIN
    FOR target IN
        SELECT DISTINCT columns.table_name
        FROM information_schema.columns AS columns
        JOIN information_schema.tables AS tables
          ON tables.table_schema = columns.table_schema
         AND tables.table_name = columns.table_name
        WHERE columns.table_schema = 'public'
          AND columns.column_name = 'school_id'
          AND tables.table_type = 'BASE TABLE'
          AND columns.table_name NOT IN (
              'core_membership',
              'core_role'
          )
        ORDER BY columns.table_name
    LOOP
        IF target.table_name = 'core_auditlog' THEN
            predicate :=
                '(school_id = app_rls_school() OR school_id IS NULL)';
        ELSE
            predicate := '(school_id = app_rls_school())';
        END IF;

        EXECUTE format(
            'ALTER TABLE %I ENABLE ROW LEVEL SECURITY',
            target.table_name
        );

        EXECUTE format(
            'DROP POLICY IF EXISTS school_isolation ON %I',
            target.table_name
        );

        EXECUTE format(
            'CREATE POLICY school_isolation ON %I '
            'USING %s WITH CHECK %s',
            target.table_name,
            predicate,
            predicate
        );
    END LOOP;
END $$;
"""

# ══════════════════════════════════════════════════════════════════
# Reverse — restore the 0036 behaviour exactly
# ══════════════════════════════════════════════════════════════════

RESTORE_BYPASS_SQL = """
CREATE OR REPLACE FUNCTION app_rls_bypass() RETURNS boolean
    LANGUAGE sql STABLE AS $$
    SELECT current_setting('app.current_school_id', true) = '*';
$$;
"""

RESTORE_RECONCILE_SQL = """
DO $$
DECLARE
    target record;
    predicate text;
BEGIN
    FOR target IN
        SELECT DISTINCT columns.table_name
        FROM information_schema.columns AS columns
        JOIN information_schema.tables AS tables
          ON tables.table_schema = columns.table_schema
         AND tables.table_name = columns.table_name
        WHERE columns.table_schema = 'public'
          AND columns.column_name = 'school_id'
          AND tables.table_type = 'BASE TABLE'
          AND columns.table_name NOT IN (
              'core_membership',
              'core_role'
          )
        ORDER BY columns.table_name
    LOOP
        IF target.table_name = 'core_auditlog' THEN
            predicate :=
                '(app_rls_bypass() OR school_id = app_rls_school() '
                'OR school_id IS NULL)';
        ELSE
            predicate :=
                '(app_rls_bypass() OR school_id = app_rls_school())';
        END IF;

        EXECUTE format(
            'ALTER TABLE %I ENABLE ROW LEVEL SECURITY',
            target.table_name
        );

        EXECUTE format(
            'DROP POLICY IF EXISTS school_isolation ON %I',
            target.table_name
        );

        EXECUTE format(
            'CREATE POLICY school_isolation ON %I '
            'USING %s WITH CHECK %s',
            target.table_name,
            predicate,
            predicate
        );
    END LOOP;
END $$;
"""


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0036_reconcile_school_rls"),
    ]

    operations = [
        migrations.RunSQL(
            sql=DISABLE_BYPASS_SQL + RECONCILE_SQL,
            reverse_sql=RESTORE_BYPASS_SQL + RESTORE_RECONCILE_SQL,
        ),
    ]

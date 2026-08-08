"""Reconcile PostgreSQL RLS coverage for school-scoped tables.

Migration 0033 hardened the then-existing school-scoped schema, but migration
ordering can allow tables from other apps to be created after it.  This
migration is anchored after the current school-scoped application leaves and
reconciles every public base table carrying a school_id column.

core_membership and core_role are intentionally excluded because they are
bootstrap tables used to resolve a user's school before tenant context exists.
"""

from django.db import migrations

HELPERS_SQL = """
CREATE OR REPLACE FUNCTION app_rls_bypass() RETURNS boolean
    LANGUAGE sql STABLE AS $$
    SELECT current_setting('app.current_school_id', true) = '*';
$$;

CREATE OR REPLACE FUNCTION app_rls_school() RETURNS uuid
    LANGUAGE sql STABLE AS $$
    SELECT CASE
        WHEN coalesce(current_setting('app.current_school_id', true), '') IN ('', '*')
            THEN NULL
        ELSE current_setting('app.current_school_id', true)::uuid
    END;
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
        ("assessments", "0009_add_performance_indexes"),
        ("core", "0035_storedfile"),
        (
            "exam_control",
            "0003_alter_examsupervisor_unique_together_and_more",
        ),
        ("notifications", "0007_deadlettermessage"),
        ("operations", "0016_add_excuse_file_validator"),
        ("quality", "0014_classroomobservation_kind"),
        ("staff_affairs", "0001_initial"),
        ("staging", "0001_initial"),
        ("student_affairs", "0001_initial"),
    ]

    operations = [
        migrations.RunSQL(
            sql=HELPERS_SQL + RECONCILE_SQL,
            reverse_sql=migrations.RunSQL.noop,
        ),
    ]

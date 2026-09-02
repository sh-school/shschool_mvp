"""Re-derive `school_isolation` on tables whose policies were written after 0037.

0037 rewrote every school-scoped policy so that tenant identity comes from the
connection role alone, and left `app_rls_bypass()` as a constant `false` so that
any policy still naming it degrades safely instead of failing. Two migrations
that landed on top of it — `academic_management.0002_rls_workload_plan` and
`operations.0024_rls_resource_subjects` — still spell their predicate as
`(app_rls_bypass() OR school_id = public.app_rls_school())`.

That predicate is harmless (`false OR x` is `x`) but it is a lie in the
schema: the contract test `[SEC-07] no policy references the bypass` exists so
nobody re-introduces a bypass by copying an old predicate, and it rightly fails
on those two. Rather than edit already-applied migrations, this one re-runs the
same reconcile loop as 0037 once more, after both of them, and — for the child
tables that carry no `school_id` of their own — rewrites their parent-join
predicates without the bypass call.

Idempotent: every statement is DROP-IF-EXISTS + CREATE.
"""

from django.db import migrations

# ══════════════════════════════════════════════════════════════════
# 1. Every table with a school_id column — same loop as 0037
# ══════════════════════════════════════════════════════════════════

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
              'core_role',
              'app_rls_role_school'
          )
        ORDER BY columns.table_name
    LOOP
        IF target.table_name = 'core_auditlog' THEN
            predicate :=
                '(school_id = public.app_rls_school() OR school_id IS NULL)';
        ELSE
            predicate := '(school_id = public.app_rls_school())';
        END IF;

        EXECUTE format(
            'ALTER TABLE %I.%I ENABLE ROW LEVEL SECURITY',
            'public',
            target.table_name
        );
        EXECUTE format(
            'DROP POLICY IF EXISTS school_isolation ON %I.%I',
            'public',
            target.table_name
        );
        EXECUTE format(
            'CREATE POLICY school_isolation ON %I.%I '
            'USING %s WITH CHECK %s',
            'public',
            target.table_name,
            predicate,
            predicate
        );
    END LOOP;
END $$;
"""

# ══════════════════════════════════════════════════════════════════
# 2. Child tables without school_id — tenant read through the parent
# ══════════════════════════════════════════════════════════════════

ALLOCATION_TABLE = "academic_management_teacherworkloadallocation"
ALLOCATION_PREDICATE = f"""EXISTS (  # noqa: S608 — ثوابتُ أسماءٍ لا مدخلات
    SELECT 1 FROM public.academic_management_teacherworkloadplan AS parent
    WHERE parent.id = {ALLOCATION_TABLE}.workload_plan_id
      AND parent.school_id = public.app_rls_school()
)"""

RESOURCE_SUBJECTS_TABLE = "operations_schedulingresource_subjects"
RESOURCE_SUBJECTS_PREDICATE = f"""EXISTS (  # noqa: S608 — ثوابتُ أسماءٍ لا مدخلات
    SELECT 1 FROM public.operations_schedulingresource AS parent
    WHERE parent.id = {RESOURCE_SUBJECTS_TABLE}.schedulingresource_id
      AND parent.school_id = public.app_rls_school()
)"""


def _policy(table: str, predicate: str) -> str:
    return f"""
ALTER TABLE public.{table} ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS school_isolation ON public.{table};
CREATE POLICY school_isolation ON public.{table}
    USING ({predicate})
    WITH CHECK ({predicate});
"""


CHILD_SQL = _policy(ALLOCATION_TABLE, ALLOCATION_PREDICATE) + _policy(
    RESOURCE_SUBJECTS_TABLE, RESOURCE_SUBJECTS_PREDICATE
)


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0047_alter_membership_joined_at"),
        ("academic_management", "0003_validation_fingerprint"),
        ("operations", "0026_scheduleslot_generation"),
    ]

    operations = [
        # لا عكسَ لهذه الهجرة: التراجعُ عنها يعني إعادةَ سياساتٍ تسمّي تجاوزاً
        # لم يعد له وجود، وهذا ليس حالةً يُرغب في العودة إليها.
        migrations.RunSQL(sql=RECONCILE_SQL, reverse_sql=migrations.RunSQL.noop),
        migrations.RunSQL(sql=CHILD_SQL, reverse_sql=migrations.RunSQL.noop),
    ]

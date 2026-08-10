"""Isolate `operations_permissionauditlog` through the permission it records.

The table logs actions taken on a `TemporaryPermission`, which carries the
school. The log itself does not.

A separate `core_permissionauditlog` exists and does carry a `school_id`. Two
tables with the same model name in different apps deserves its own audit, but
that question does not bear on this one: whatever the outcome, this table holds
tenant rows today and its migration says so plainly. Leaving it unpoliced while
the naming is investigated would be the wrong order.
"""

from django.db import migrations

TABLE = "operations_permissionauditlog"

PREDICATE = f"""
EXISTS (
    SELECT 1
    FROM public.operations_temporarypermission AS parent
    WHERE parent.id = {TABLE}.temp_permission_id
      AND parent.school_id = public.app_rls_school()
)
"""

ENABLE_SQL = f"""
ALTER TABLE public.{TABLE} ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS school_isolation ON public.{TABLE};

CREATE POLICY school_isolation ON public.{TABLE}
    USING ({PREDICATE})
    WITH CHECK ({PREDICATE});
"""

DISABLE_SQL = f"""
DROP POLICY IF EXISTS school_isolation ON public.{TABLE};
ALTER TABLE public.{TABLE} DISABLE ROW LEVEL SECURITY;
"""


class Migration(migrations.Migration):
    dependencies = [
        ("operations", "0016_add_excuse_file_validator"),
        ("core", "0037_rls_tenant_identity_from_db_role"),
    ]

    operations = [
        migrations.RunSQL(sql=ENABLE_SQL, reverse_sql=DISABLE_SQL),
    ]

"""Isolate `core_behaviorpointrecovery` through its parent infraction.

The table records a point recovery granted against a `BehaviorInfraction`. It
carries no `school_id`, so migration 0037's reconcile loop — which selects
tables on that column — never saw it. It is not an oversight in the loop; the
loop cannot police a column that does not exist.

The alternative was to add a duplicate `school_id`. That would create a second
copy of a fact the parent already holds, and a second copy can disagree with the
first. Reading the parent leaves exactly one answer to the question of which
school a recovery belongs to.

The subquery is itself subject to the parent's own policy, which reinforces the
predicate rather than weakening it: an infraction the current role cannot see
cannot satisfy the EXISTS either.
"""

from django.db import migrations

TABLE = "core_behaviorpointrecovery"

PREDICATE = f"""
EXISTS (
    SELECT 1
    FROM public.core_behaviorinfraction AS parent
    WHERE parent.id = {TABLE}.infraction_id
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
        ("behavior", "0013_encrypt_sensitive_text"),
        ("core", "0037_rls_tenant_identity_from_db_role"),
    ]

    operations = [
        migrations.RunSQL(sql=ENABLE_SQL, reverse_sql=DISABLE_SQL),
    ]

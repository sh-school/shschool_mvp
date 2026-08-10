"""Isolate `core_studentenrollment` through its class group.

An enrolment links a student to a `ClassGroup`, and the class group carries the
school. The enrolment itself does not, so migration 0037's reconcile loop could
not reach it.

Deriving from the parent rather than adding a duplicate column keeps a single
answer to which school an enrolment belongs to. `student_id` is deliberately not
part of the predicate: a person's tenancy is a many-to-many through
`core_membership`, so it would widen the predicate rather than narrow it.
"""

from django.db import migrations

TABLE = "core_studentenrollment"

PREDICATE = f"""
EXISTS (
    SELECT 1
    FROM public.core_classgroup AS parent
    WHERE parent.id = {TABLE}.class_group_id
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
        ("core", "0037_rls_tenant_identity_from_db_role"),
    ]

    operations = [
        migrations.RunSQL(sql=ENABLE_SQL, reverse_sql=DISABLE_SQL),
    ]

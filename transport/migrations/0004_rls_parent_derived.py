"""Isolate bus routes and the route-students join table.

`core_busroute` derives its school from the bus it runs on.

`core_busroute_students` is the join table Django creates for
`BusRoute.students`. It is two hops from a school — route, then bus — and it
holds two tenant-bearing references, not one: the route on one side and the
student on the other. Policing only the route would leave the association open
in the direction that matters most, since a route belonging to this school
could still list a student who belongs to another. A foreign key cannot prevent
it: PostgreSQL evaluates referential integrity outside row-level security, so
the key is satisfied either way.

The student side cannot be reached by a column. `core_customuser` carries no
`school_id` — a person's tenancy is a many-to-many through `core_membership` —
so the check asks that table directly: the referenced user must hold a
membership in the current school. Someone enrolled in two schools may be listed
in each, because each school's role satisfies the predicate on its own turn;
only a student with no membership here is refused.

`USING` stays on the route alone, deliberately. Reading and deleting an
existing association must keep working even if the student's membership was
later removed — tightening `USING` would hide rows the school still owns and
would take away the means to correct them. `WITH CHECK` governs what may be
written, and that is where the second reference belongs.
"""

from django.db import migrations

CURRENT = "public.app_rls_school()"

ROUTE = "core_busroute"
ROUTE_PREDICATE = f"""
EXISTS (
    SELECT 1
    FROM public.core_schoolbus AS bus
    WHERE bus.id = {ROUTE}.bus_id
      AND bus.school_id = {CURRENT}
)
"""

ROUTE_STUDENTS = "core_busroute_students"
ROUTE_STUDENTS_USING = f"""
EXISTS (
    SELECT 1
    FROM public.core_busroute AS route
    JOIN public.core_schoolbus AS bus ON bus.id = route.bus_id
    WHERE route.id = {ROUTE_STUDENTS}.busroute_id
      AND bus.school_id = {CURRENT}
)
"""
ROUTE_STUDENTS_CHECK = f"""
{ROUTE_STUDENTS_USING}
AND EXISTS (
    SELECT 1
    FROM public.core_membership AS m
    WHERE m.user_id = {ROUTE_STUDENTS}.customuser_id
      AND m.school_id = {CURRENT}
)
"""


def _enable(table, using, check):
    return f"""
ALTER TABLE public.{table} ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS school_isolation ON public.{table};

CREATE POLICY school_isolation ON public.{table}
    USING ({using})
    WITH CHECK ({check});
"""


def _disable(table):
    return f"""
DROP POLICY IF EXISTS school_isolation ON public.{table};
ALTER TABLE public.{table} DISABLE ROW LEVEL SECURITY;
"""


class Migration(migrations.Migration):
    dependencies = [
        ("transport", "0003_encrypt_driver_contact"),
        ("core", "0037_rls_tenant_identity_from_db_role"),
    ]

    operations = [
        migrations.RunSQL(
            sql=_enable(ROUTE, ROUTE_PREDICATE, ROUTE_PREDICATE),
            reverse_sql=_disable(ROUTE),
        ),
        migrations.RunSQL(
            sql=_enable(ROUTE_STUDENTS, ROUTE_STUDENTS_USING, ROUTE_STUDENTS_CHECK),
            reverse_sql=_disable(ROUTE_STUDENTS),
        ),
    ]

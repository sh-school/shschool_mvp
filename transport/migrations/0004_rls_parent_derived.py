"""Isolate bus routes and the route-students join table.

`core_busroute` derives its school from the bus it runs on.

`core_busroute_students` is the join table Django creates for
`BusRoute.students`. It is two hops from a school — route, then bus — and until
now nothing prevented a route belonging to one school from listing a student
enrolled in another. A foreign key cannot prevent it: PostgreSQL evaluates
referential integrity outside row-level security, so the key would have been
satisfied either way.

As with library participants, only the route side is policed. The other side is
`core_customuser`, whose tenancy is a many-to-many through `core_membership`.
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
ROUTE_STUDENTS_PREDICATE = f"""
EXISTS (
    SELECT 1
    FROM public.core_busroute AS route
    JOIN public.core_schoolbus AS bus ON bus.id = route.bus_id
    WHERE route.id = {ROUTE_STUDENTS}.busroute_id
      AND bus.school_id = {CURRENT}
)
"""


def _enable(table, predicate):
    return f"""
ALTER TABLE public.{table} ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS school_isolation ON public.{table};

CREATE POLICY school_isolation ON public.{table}
    USING ({predicate})
    WITH CHECK ({predicate});
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
            sql=_enable(ROUTE, ROUTE_PREDICATE),
            reverse_sql=_disable(ROUTE),
        ),
        migrations.RunSQL(
            sql=_enable(ROUTE_STUDENTS, ROUTE_STUDENTS_PREDICATE),
            reverse_sql=_disable(ROUTE_STUDENTS),
        ),
    ]

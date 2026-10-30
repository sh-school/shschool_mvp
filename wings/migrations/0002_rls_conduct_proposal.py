"""عزلُ اقتراحات المخالفات (wings.ConductProposal) عن باقي المدارس — بصيغة `0084` نفسِها (`school_id` مباشرةً، بلا `app_rls_bypass`)."""

from django.db import migrations

TABLES = ("wings_conductproposal",)
PREDICATE = "(school_id = public.app_rls_school())"


def _enable(table: str) -> str:
    return f"""
ALTER TABLE public.{table} ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS school_isolation ON public.{table};
CREATE POLICY school_isolation ON public.{table}
    USING ({PREDICATE})
    WITH CHECK ({PREDICATE});
"""


def _disable(table: str) -> str:
    return f"""
DROP POLICY IF EXISTS school_isolation ON public.{table};
ALTER TABLE public.{table} DISABLE ROW LEVEL SECURITY;
"""


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0037_rls_tenant_identity_from_db_role"),
        ("wings", "0001_conduct_proposal"),
    ]

    operations = [migrations.RunSQL(sql=_enable(t), reverse_sql=_disable(t)) for t in TABLES]

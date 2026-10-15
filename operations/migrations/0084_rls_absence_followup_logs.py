"""عزلُ سجلّي متابعة الغياب (بياناتُ قاصرين وتغذيةٌ مشفَّرة) عن باقي المدارس — بصيغة `0069` نفسِها.

الجدولان يحملان `school_id` فيُسنَد إليهما مباشرةً، والهويّةُ من دور الاتصال بلا `app_rls_bypass`.
"""

from django.db import migrations

TABLES = ("operations_absencecontactlog", "operations_absenceactionlog")
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
        ("operations", "0083_absence_followup_logs"),
    ]

    operations = [migrations.RunSQL(sql=_enable(t), reverse_sql=_disable(t)) for t in TABLES]

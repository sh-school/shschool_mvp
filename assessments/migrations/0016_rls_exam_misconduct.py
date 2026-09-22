"""عزلُ وقائع انضباط الاختبارات (`ExamMisconduct`) عن باقي المدارس — بصيغة `0012`.

جدولٌ يُنشأ بعد `core.0037` يُعزل بترحيله؛ وهو يحمل `school_id` فالسياسةُ مباشرة.
"""

from django.db import migrations

TABLE = "assessments_exammisconduct"
PREDICATE = "(school_id = public.app_rls_school())"

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
        ("assessments", "0015_verdict_round6_misconduct_pass_mark_ruleset"),
        ("core", "0037_rls_tenant_identity_from_db_role"),
    ]

    operations = [migrations.RunSQL(sql=ENABLE_SQL, reverse_sql=DISABLE_SQL)]

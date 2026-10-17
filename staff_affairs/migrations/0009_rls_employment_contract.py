"""عزلُ عقد التوظيف وفترة الاختبار بالمدرسة (RLS) — بصيغة `0069` نفسِها كباقي جداول شؤون الموظفين.

الجدولُ يحمل `school_id` فيُسنَد إليه مباشرةً، والهويّةُ من دور الاتصال بلا `app_rls_bypass`.
هجرةٌ مستقلّةٌ صنوُ `0008` (W-20261001-027): `0008` أنشأت الجدول بلا عزلٍ فتأتي هذه بالسياسة.
"""

from django.db import migrations

TABLE = "staff_affairs_employmentcontract"
PREDICATE = f"{TABLE}.school_id = public.app_rls_school()"

ENABLE = f"""
ALTER TABLE public.{TABLE} ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS school_isolation ON public.{TABLE};

CREATE POLICY school_isolation ON public.{TABLE}
    USING ({PREDICATE})
    WITH CHECK ({PREDICATE});
"""
DISABLE = f"""
DROP POLICY IF EXISTS school_isolation ON public.{TABLE};
ALTER TABLE public.{TABLE} DISABLE ROW LEVEL SECURITY;
"""


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0037_rls_tenant_identity_from_db_role"),
        ("staff_affairs", "0008_employment_contract"),
    ]

    operations = [migrations.RunSQL(sql=ENABLE, reverse_sql=DISABLE)]

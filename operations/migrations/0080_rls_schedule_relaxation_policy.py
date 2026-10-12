"""عزلُ سياسة تخفيف التلاصق المدرسيّة عن باقي المدارس — بالصيغة المعتمَدة بعد `core/0037`.

الجدولُ يحمل `school_id` فيُسنَد إليه مباشرةً، والهويّةُ من دور الاتصال **بلا `app_rls_bypass`**. مطابقةُ `core/0037` وقعت قبل إنشائه
فتُضاف هنا صراحةً (W-20261011-007). هجرةٌ على جدولٍ جديدٍ وحده؛ لا تمسّ ScheduleSlot ولا الجدولَ المعتمد (D-381م).
"""

from django.db import migrations

TABLE = "operations_schedulerelaxationpolicy"
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
        ("core", "0037_rls_tenant_identity_from_db_role"),
        ("operations", "0079_schedule_relaxation_policy"),
    ]

    operations = [
        migrations.RunSQL(sql=ENABLE_SQL, reverse_sql=DISABLE_SQL),
    ]

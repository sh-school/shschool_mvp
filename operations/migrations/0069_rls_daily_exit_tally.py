"""عزلُ ملخّص الخروج اليوميّ (بياناتُ قاصرين) عن باقي المدارس — بالصيغة المعتمَدة بعد `core/0037`.

الجدولُ يحمل `school_id` فيُسنَد إليه مباشرةً، والهويّةُ من دور الاتصال **بلا `app_rls_bypass`**. وهجرةٌ جديدةٌ لا تعديلٌ لـ0066–0068
(لم تُنشَر بعد لكنّ الجديدةَ أسلم). مطابقةُ `core/0037` تقع عند إنشائها فلا تشمل جدولاً أُنشئ بعدها — فتُضاف هنا صراحةً.
"""

from django.db import migrations

TABLE = "operations_dailyexittally"
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
        ("operations", "0068_daily_exit_tally_by_destination"),
    ]

    operations = [
        migrations.RunSQL(sql=ENABLE_SQL, reverse_sql=DISABLE_SQL),
    ]

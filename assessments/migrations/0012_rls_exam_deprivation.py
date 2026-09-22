"""عزلُ قرارات الحرمان (`ExamDeprivation`) عن باقي المدارس — بصيغة `core/0037`.

`core.0037` فعّل العزلَ على كلّ جدولٍ يحمل `school_id` يومَ كُتب، وهي مطابقةٌ لا
تُعاد؛ فجدولٌ يُنشأ بعدها يُعزل بترحيله. والجدولُ يحمل `school_id` فالسياسةُ
مباشرة، والهويّةُ من دور الاتصال (`app_rls_school()`).
"""

from django.db import migrations

TABLE = "assessments_examdeprivation"
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
        ("assessments", "0011_verdict_standing_deprivation"),
        ("core", "0037_rls_tenant_identity_from_db_role"),
    ]

    operations = [migrations.RunSQL(sql=ENABLE_SQL, reverse_sql=DISABLE_SQL)]

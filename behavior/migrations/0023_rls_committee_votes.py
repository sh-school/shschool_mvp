"""عزلُ `behavior_behaviorcommitteevote` بالمخالفة الأمّ (W-024، سقّاطة تصنيف المستأجِرين).

الجدول لا يحمل `school_id`؛ مدرستُه مدرسةُ المخالفة التي يُصوَّت عليها. فالسياسةُ تقرأ
الأبَ كما في `0014_rls_parent_derived` بدل نسخةٍ ثانيةٍ من العمود قد تنحرف عنه.
"""

from django.db import migrations

TABLE = "behavior_behaviorcommitteevote"

PREDICATE = f"""
EXISTS (
    SELECT 1
    FROM public.core_behaviorinfraction AS parent
    WHERE parent.id = {TABLE}.infraction_id
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
        ("behavior", "0022_committee_votes"),
        ("core", "0037_rls_tenant_identity_from_db_role"),
    ]

    operations = [
        migrations.RunSQL(sql=ENABLE_SQL, reverse_sql=DISABLE_SQL),
    ]

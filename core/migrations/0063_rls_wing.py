"""عزلُ جدول الأجنحة على مستوى الصفّ في PostgreSQL.

`core.0037` فعّل العزلَ على كلّ جدولٍ يحمل `school_id` **يومَ كُتب**، وهي
مطابقةٌ لا تُعاد. فجدولٌ يُنشأ بعدها يخرج بلا عزلٍ ولا سياسة — والحارسان
`test_parent_derived_rls` و`test_rls_middleware` يسمّيانه فوراً. وهذا صوابُ
التصميم: طبقةُ التطبيق تكفي ما دامت المدرسةُ واحدة، والقاعدةُ وحدها تكفي حين
تصير اثنتين، فلا يُترك جدولٌ مستأجَرٌ بلا حارسٍ في القاعدة.

والجناحُ يحمل `school_id` بنفسه، فالسياسةُ مباشرةٌ لا مشتقّةٌ من أب. والهويّةُ
في `app_rls_school()` تُشتقّ من دور الاتصال لا من متغيّرِ جلسةٍ يضبطه أيُّ
دور — كما استقرّ عليه الأمر في `core.0037`.
"""

from django.db import migrations

TABLE = "core_wing"
CURRENT = "public.app_rls_school()"
PREDICATE = f"{TABLE}.school_id = {CURRENT}"

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
        ("core", "0062_time_band_floor"),
        ("core", "0037_rls_tenant_identity_from_db_role"),
    ]

    operations = [migrations.RunSQL(sql=ENABLE, reverse_sql=DISABLE)]

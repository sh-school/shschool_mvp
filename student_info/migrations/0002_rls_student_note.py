"""عزلُ جدول الملاحظات على مستوى الصفّ في PostgreSQL.

الجدولُ يحمل `school_id` بنفسه، فالسياسةُ مباشرةٌ لا مشتقّةٌ من أب. وهو
يستحقّها أكثر من أكثر الجداول: نصُّ ملاحظةٍ نفسيّةٍ عن قاصر. وطبقةُ التطبيق
تكفي ما دامت المدرسةُ واحدة، والقاعدةُ وحدها تكفي حين تصير اثنتين.

والهويّةُ في `app_rls_school()` تُشتقّ من دور الاتصال بالقاعدة لا من متغيّرِ
جلسةٍ يضبطه أيُّ دور — كما استقرّ عليه الأمر في `core.0037`.
"""

from django.db import migrations

TABLE = "student_info_studentnote"
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
        ("student_info", "0001_initial"),
        ("core", "0037_rls_tenant_identity_from_db_role"),
    ]

    operations = [migrations.RunSQL(sql=ENABLE, reverse_sql=DISABLE)]

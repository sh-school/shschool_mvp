"""عزلُ الخطّة الدراسيّة عن باقي المدارس — سلوكاً في القاعدة لا إعلاناً في الكود.

الجدولُ يحمل `school_id` فيُسنَد إليه مباشرةً، والصيغةُ هي الصيغةُ المعتمَدةُ
بعد `core/0037`: الهويّةُ من دور الاتصال، **وبلا `app_rls_bypass`**. فالتجاوزُ
أُزيل من السياسات كلِّها هناك، ونسخُ الصيغة القديمة من `0002` كان يُعيده من
بابٍ خلفيّ في جدولٍ جديد — ولا يكشفه إلّا اختبارُ العقد.

وسياسةُ `academic_management_teachersubjectqualification` لا تُحذف هنا: القاعدةُ
تُسقط سياساتِ الجدول مع الجدول، وقد حُذف في `0004`.
"""

from django.db import migrations

TABLE = "academic_management_curriculumplan"
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
        ("academic_management", "0004_curriculum_plan"),
    ]

    operations = [
        migrations.RunSQL(sql=ENABLE_SQL, reverse_sql=DISABLE_SQL),
    ]

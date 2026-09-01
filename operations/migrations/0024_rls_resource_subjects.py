"""عزلُ موارد الجدولة وجدولِ ربطها بالموادّ.

`SchedulingResource` يحمل `school_id` فيُسنَد إليه مباشرةً — لكنّ حلقةَ
`core/0036` جرت قبل وجوده، فلا تشمله. والجداولُ التي تُنشَأ بعد تلك الحلقة
تحتاج ترحيلَها الخاصّ، وإلّا بقيت بلا سياسةٍ في قاعدةٍ كلُّ جاراتِها معزولة.

وجدولُ الربط الذي أنشأه Django للـ`ManyToManyField` لا يحمل `school_id` عمداً:
عمودٌ مكرّرٌ نسخةٌ ثانيةٌ من حقيقةٍ يقولها الأب.

والحارسُ الساكنُ في `core/tenancy.py` كشف الأوّلَ، واختبارُ السلوك كشف الثاني.
"""

from django.db import migrations

PARENT = "operations_schedulingresource"
TABLE = "operations_schedulingresource_subjects"

PARENT_PREDICATE = "(app_rls_bypass() OR school_id = public.app_rls_school())"

PREDICATE = f"""
EXISTS (
    SELECT 1
    FROM public.operations_schedulingresource AS parent
    WHERE parent.id = {TABLE}.schedulingresource_id
      AND parent.school_id = public.app_rls_school()
)
"""

ENABLE_SQL = f"""
ALTER TABLE public.{PARENT} ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS school_isolation ON public.{PARENT};
CREATE POLICY school_isolation ON public.{PARENT}
    USING ({PARENT_PREDICATE})
    WITH CHECK ({PARENT_PREDICATE});

ALTER TABLE public.{TABLE} ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS school_isolation ON public.{TABLE};
CREATE POLICY school_isolation ON public.{TABLE}
    USING ({PREDICATE})
    WITH CHECK ({PREDICATE});
"""

DISABLE_SQL = f"""
DROP POLICY IF EXISTS school_isolation ON public.{TABLE};
ALTER TABLE public.{TABLE} DISABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS school_isolation ON public.{PARENT};
ALTER TABLE public.{PARENT} DISABLE ROW LEVEL SECURITY;
"""


class Migration(migrations.Migration):
    dependencies = [
        ("operations", "0023_schedulingresource"),
        ("core", "0040_rls_academic_calendar"),
    ]

    operations = [
        migrations.RunSQL(sql=ENABLE_SQL, reverse_sql=DISABLE_SQL),
    ]

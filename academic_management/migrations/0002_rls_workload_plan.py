"""عزلُ جداول الأنصبة عن باقي المدارس — سلوكاً في القاعدة لا إعلاناً في الكود.

ثلاثةُ جداولَ تحمل `school_id` فتُسنَد إليه مباشرةً، ورابعٌ لا يحمله عمداً:
`TeacherWorkloadAllocation` يستمدّ مدرستَه من خطّته، لأنّ عموداً مكرّراً نسخةٌ
ثانيةٌ من حقيقةٍ يقولها الأب — وفرصةٌ ثانيةٌ لمخالفته.

ولا يكفي أن تُصنَّف الجداولُ في `core/tenancy.py`: الحارسُ الساكن يُثبت أنّ
التصميمَ معلَن، وهذا الترحيلُ وحدَه يُثبت أنّ المحرّكَ نفّذه.

والنمطُ منقولٌ حرفيّاً عن `core/0036` و`core/0040` كي لا تختلف صيغةُ السياسة
بين جدولٍ وآخر.
"""

from django.db import migrations

DIRECT_TABLES = (
    "academic_management_teacherworkloadplan",
    "academic_management_teachersubjectqualification",
    "academic_management_workloadgovernance",
)

CHILD_TABLE = "academic_management_teacherworkloadallocation"

DIRECT_PREDICATE = "(app_rls_bypass() OR school_id = public.app_rls_school())"

CHILD_PREDICATE = f"""
EXISTS (
    SELECT 1
    FROM public.academic_management_teacherworkloadplan AS parent
    WHERE parent.id = {CHILD_TABLE}.workload_plan_id
      AND parent.school_id = public.app_rls_school()
)
"""


def _enable(table: str, predicate: str) -> str:
    return f"""
ALTER TABLE public.{table} ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS school_isolation ON public.{table};

CREATE POLICY school_isolation ON public.{table}
    USING ({predicate})
    WITH CHECK ({predicate});
"""


def _disable(table: str) -> str:
    return f"""
DROP POLICY IF EXISTS school_isolation ON public.{table};
ALTER TABLE public.{table} DISABLE ROW LEVEL SECURITY;
"""


ENABLE_SQL = "\n".join(
    [_enable(t, DIRECT_PREDICATE) for t in DIRECT_TABLES] + [_enable(CHILD_TABLE, CHILD_PREDICATE)]
)

DISABLE_SQL = "\n".join(_disable(t) for t in (*DIRECT_TABLES, CHILD_TABLE))


class Migration(migrations.Migration):
    dependencies = [
        ("academic_management", "0001_initial"),
        ("core", "0040_rls_academic_calendar"),
    ]

    operations = [
        migrations.RunSQL(sql=ENABLE_SQL, reverse_sql=DISABLE_SQL),
    ]

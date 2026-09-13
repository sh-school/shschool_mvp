# `operations_scheduleconstraintoverride` أُنشئ بعد مسح 0048 (core) لجداول
# school_id، فيأخذ سياسةَ المستأجر نفسَها — fail-closed كما في بقيّة الجداول.
#
# واستثناءُ قيدٍ يخصّ مدرسةً بعينها: لا يُقرأ ولا يُكتب من سياق مدرسةٍ أخرى.

from django.db import migrations

FORWARD = """
ALTER TABLE public.operations_scheduleconstraintoverride ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS school_isolation ON public.operations_scheduleconstraintoverride;
CREATE POLICY school_isolation ON public.operations_scheduleconstraintoverride
    USING (school_id = public.app_rls_school())
    WITH CHECK (school_id = public.app_rls_school());
"""

BACKWARD = """
DROP POLICY IF EXISTS school_isolation ON public.operations_scheduleconstraintoverride;
ALTER TABLE public.operations_scheduleconstraintoverride DISABLE ROW LEVEL SECURITY;
"""


class Migration(migrations.Migration):
    dependencies = [
        ("operations", "0039_schedule_constraint_override"),
        ("core", "0037_rls_tenant_identity_from_db_role"),
    ]

    operations = [
        migrations.RunSQL(FORWARD, BACKWARD),
    ]

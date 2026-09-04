# `operations_schedulebaseline` أُنشئ بعد مسح 0048 (core) لجداول school_id، فيأخذ
# سياسةَ المستأجر نفسَها — fail-closed كما في بقيّة الجداول.

from django.db import migrations

FORWARD = """
ALTER TABLE public.operations_schedulebaseline ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS school_isolation ON public.operations_schedulebaseline;
CREATE POLICY school_isolation ON public.operations_schedulebaseline
    USING (school_id = public.app_rls_school())
    WITH CHECK (school_id = public.app_rls_school());
"""

BACKWARD = """
DROP POLICY IF EXISTS school_isolation ON public.operations_schedulebaseline;
ALTER TABLE public.operations_schedulebaseline DISABLE ROW LEVEL SECURITY;
"""


class Migration(migrations.Migration):
    dependencies = [
        ("operations", "0033_subject_pedagogy_generation_metrics_baseline"),
    ]

    operations = [
        migrations.RunSQL(FORWARD, BACKWARD),
    ]

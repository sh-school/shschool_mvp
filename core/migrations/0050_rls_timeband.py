# `core_timeband` أُنشئ بعد 0048 التي تمسح جداول school_id وقت تشغيلها، فبقي
# بلا سياسة عزلٍ: الجدولُ يحمل school_id فيأخذ سياسةَ المستأجر نفسَها
# (fail-closed كما في بقيّة الجداول).

from django.db import migrations

FORWARD = """
ALTER TABLE public.core_timeband ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS school_isolation ON public.core_timeband;
CREATE POLICY school_isolation ON public.core_timeband
    USING (school_id = public.app_rls_school())
    WITH CHECK (school_id = public.app_rls_school());
"""

BACKWARD = """
DROP POLICY IF EXISTS school_isolation ON public.core_timeband;
ALTER TABLE public.core_timeband DISABLE ROW LEVEL SECURITY;
"""


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0049_timeband_classgroup_time_band"),
    ]

    operations = [
        migrations.RunSQL(FORWARD, BACKWARD),
    ]

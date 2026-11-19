"""عزلُ جدول مُهَل وجهات الخروج بين المدارس — بصيغة `0089` نفسِها (إعدادٌ مدرسيّ يحمل `school_id`)."""

from django.db import migrations

TABLES = ("operations_exitdestinationgrace",)
PREDICATE = "(school_id = public.app_rls_school())"


def _enable(table: str) -> str:
    return f"""
ALTER TABLE public.{table} ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS school_isolation ON public.{table};
CREATE POLICY school_isolation ON public.{table}
    USING ({PREDICATE})
    WITH CHECK ({PREDICATE});
"""


def _disable(table: str) -> str:
    return f"""
DROP POLICY IF EXISTS school_isolation ON public.{table};
ALTER TABLE public.{table} DISABLE ROW LEVEL SECURITY;
"""


class Migration(migrations.Migration):
    dependencies = [("operations", "0101_exit_card_states")]

    operations = [migrations.RunSQL(sql=_enable(t), reverse_sql=_disable(t)) for t in TABLES]

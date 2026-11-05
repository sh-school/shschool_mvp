"""عزلُ وثائق المعرفة ومقاطعها عن باقي المدارس — بالصيغة المعتمَدة بعد `core/0037`.

الجدولان يحملان `school_id` فيُسنَدان مباشرةً إلى `public.app_rls_school()`، والهويّةُ من دور
الاتصال بلا `app_rls_bypass` (كما في `academic_management/0007`).
"""

from django.db import migrations

TABLES = ("local_ai_knowledgedocument", "local_ai_documentchunk")
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
    dependencies = [
        ("local_ai", "0001_initial"),
    ]

    operations = [
        migrations.RunSQL(sql=_enable(table), reverse_sql=_disable(table)) for table in TABLES
    ]

"""عزلُ جدولَي استثناءات الحضور (نموذج 03) والإنابة عن المدير على مستوى الصفّ.

على نهج ``0004``: كلٌّ منهما يحمل ``school_id`` بنفسه، فالسياسةُ مباشرة، والهويّةُ من
``app_rls_school()`` — دورُ الاتصال لا متغيّرُ جلسة.
"""

from django.db import migrations

CURRENT = "public.app_rls_school()"
TABLES = ("staff_affairs_attendanceexception", "staff_affairs_principaldelegation")


def _enable(table: str) -> str:
    predicate = f"{table}.school_id = {CURRENT}"
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


class Migration(migrations.Migration):
    dependencies = [
        ("staff_affairs", "0006_permit_two_boxes_exceptions_delegation"),
        ("core", "0037_rls_tenant_identity_from_db_role"),
    ]

    operations = [
        migrations.RunSQL(sql=_enable(table), reverse_sql=_disable(table)) for table in TABLES
    ]

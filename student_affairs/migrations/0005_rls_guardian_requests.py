"""عزلُ طلبات الأولياء وأحداثِ مساراتها عن باقي المدارس (W-20261001-019، سقّاطة تصنيف المستأجِرين).

`student_affairs_guardianrequest` يحمل `school_id` فسياستُه مباشرة؛ و`..._guardianrequestevent` لا يحمله،
فمدرستُه مدرسةُ الطلب الأمّ كما في `behavior.0023` بدل نسخةٍ ثانيةٍ من العمود قد تنحرف عنه.
"""

from django.db import migrations

REQUESTS = "student_affairs_guardianrequest"
EVENTS = "student_affairs_guardianrequestevent"

DIRECT_PREDICATE = "(school_id = public.app_rls_school())"
EVENT_PREDICATE = f"""
EXISTS (
    SELECT 1
    FROM public.{REQUESTS} AS parent
    WHERE parent.id = {EVENTS}.request_id
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


class Migration(migrations.Migration):
    dependencies = [
        ("student_affairs", "0004_guardian_requests"),
        ("core", "0037_rls_tenant_identity_from_db_role"),
    ]

    operations = [
        migrations.RunSQL(sql=_enable(REQUESTS, DIRECT_PREDICATE), reverse_sql=_disable(REQUESTS)),
        migrations.RunSQL(sql=_enable(EVENTS, EVENT_PREDICATE), reverse_sql=_disable(EVENTS)),
    ]

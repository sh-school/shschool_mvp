"""عزلُ جدول طلبات الالتحاق على مستوى الصفّ في PostgreSQL (W-20261001-033).

الجدولُ يحمل `school_id` بنفسه فالسياسةُ مباشرة، والهويّةُ تُشتقّ من دور الاتصال
(`app_rls_school()`) كما استقرّ في `core.0037`.
"""

from django.db import migrations

TABLE = "student_affairs_admissionapplication"
PREDICATE = f"{TABLE}.school_id = public.app_rls_school()"

ENABLE = f"""
ALTER TABLE public.{TABLE} ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS school_isolation ON public.{TABLE};

CREATE POLICY school_isolation ON public.{TABLE}
    USING ({PREDICATE})
    WITH CHECK ({PREDICATE});
"""

DISABLE = f"""
DROP POLICY IF EXISTS school_isolation ON public.{TABLE};
ALTER TABLE public.{TABLE} DISABLE ROW LEVEL SECURITY;
"""


class Migration(migrations.Migration):
    dependencies = [
        ("student_affairs", "0006_admission_application"),
        ("core", "0037_rls_tenant_identity_from_db_role"),
    ]

    operations = [migrations.RunSQL(sql=ENABLE, reverse_sql=DISABLE)]

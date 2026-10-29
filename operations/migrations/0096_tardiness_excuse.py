"""عذرُ التأخّر عن الحصّة (W-20261002-028): جدولٌ جديد فقط — توسيعٌ لا يحذف ولا يغيّر شيئاً قائماً، وعزلُ المدارس بصيغة `0089` نفسِها."""

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models

import operations.models.common


TABLE = "operations_tardinessexcuse"
PREDICATE = "(school_id = public.app_rls_school())"
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
        ("core", "0037_rls_tenant_identity_from_db_role"),
        ("operations", "0095_rls_absence_report_snapshot"),
    ]

    operations = [
        migrations.CreateModel(
            name="TardinessExcuse",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=operations.models.common._uuid,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                (
                    "reason",
                    models.CharField(blank=True, max_length=300, verbose_name="بيان العذر"),
                ),
                (
                    "granted_at",
                    models.DateTimeField(auto_now_add=True, verbose_name="وقتُ الاعتماد"),
                ),
                (
                    "attendance",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="tardiness_excuse",
                        to="operations.studentattendance",
                        verbose_name="سجلُّ التأخّر",
                    ),
                ),
                (
                    "granted_by",
                    models.ForeignKey(
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="tardiness_excuses_granted",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="اعتمده المعلّم",
                    ),
                ),
                (
                    "school",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="tardiness_excuses",
                        to="core.school",
                        verbose_name="المدرسة",
                    ),
                ),
            ],
            options={
                "verbose_name": "عذرُ تأخّر",
                "verbose_name_plural": "أعذارُ التأخّر",
            },
        ),
        migrations.RunSQL(sql=ENABLE, reverse_sql=DISABLE),
    ]

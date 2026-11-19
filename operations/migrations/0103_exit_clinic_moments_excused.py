"""إدارةُ الأجنحة 3/4: لحظتا العيادة على `ClassExit` وجدولُ «الخروج المبرَّر الدائم» بعزل RLS.

إضافةٌ كلُّها (حقلان قابلان للفراغ وجدولٌ جديد): التراجعُ يحذفها بلا فقدِ بياناتٍ سابقة.
"""

import uuid

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models

PREDICATE = "(school_id = public.app_rls_school())"
TABLE = "operations_excusedexit"


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0087_wing_assignment"),
        ("operations", "0102_rls_exit_destination_grace"),
    ]

    operations = [
        migrations.AddField(
            model_name="classexit",
            name="clinic_arrived_at",
            field=models.DateTimeField(blank=True, null=True, verbose_name="وصل العيادة"),
        ),
        migrations.AddField(
            model_name="classexit",
            name="clinic_left_at",
            field=models.DateTimeField(blank=True, null=True, verbose_name="غادر العيادة"),
        ),
        migrations.CreateModel(
            name="ExcusedExit",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4, editable=False, primary_key=True, serialize=False
                    ),
                ),
                ("starts_on", models.DateField(verbose_name="من")),
                ("ends_on", models.DateField(verbose_name="إلى")),
                ("set_by_role", models.CharField(max_length=20, verbose_name="دورُ واضعه")),
                (
                    "reason",
                    models.TextField(blank=True, verbose_name="السبب (لواضعه وحدَه)"),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True, verbose_name="وُضع في")),
                (
                    "school",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="excused_exits",
                        to="core.school",
                        verbose_name="المدرسة",
                    ),
                ),
                (
                    "set_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="excused_exits_set",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="وضعه",
                    ),
                ),
                (
                    "student",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="excused_exits",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="الطالب",
                    ),
                ),
            ],
            options={
                "verbose_name": "خروجٌ مبرَّرٌ دائم",
                "verbose_name_plural": "خروجٌ مبرَّرٌ دائم",
                "indexes": [
                    models.Index(
                        fields=["school", "student", "ends_on"],
                        name="excused_exit_student_idx",
                    )
                ],
                "constraints": [
                    models.CheckConstraint(
                        condition=models.Q(("ends_on__gte", models.F("starts_on"))),
                        name="excused_exit_range_valid",
                    )
                ],
            },
        ),
        migrations.RunSQL(
            sql=f"""
ALTER TABLE public.{TABLE} ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS school_isolation ON public.{TABLE};
CREATE POLICY school_isolation ON public.{TABLE}
    USING ({PREDICATE})
    WITH CHECK ({PREDICATE});
""",
            reverse_sql=f"""
DROP POLICY IF EXISTS school_isolation ON public.{TABLE};
ALTER TABLE public.{TABLE} DISABLE ROW LEVEL SECURITY;
""",
        ),
    ]

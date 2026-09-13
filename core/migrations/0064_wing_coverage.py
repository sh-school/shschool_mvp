"""سجلُّ تغطية الأجنحة — ومعه امتدادُ `btree_gist` وعزلُ الصفّ.

**`btree_gist`**: قيدُ الاستبعاد على (الجناح، المدّة) يخلط نوعين — مساواةَ
مفتاحٍ أجنبيٍّ وتداخلَ مدّة. وفهرسُ GiST وحدَه يقبل التداخل، ولا يقبل
المساواةَ على `uuid` إلّا بهذا الامتداد. وسابقتُه في المستودع `pg_trgm`
(هجرة `core/0012`).

**عزلُ الصفّ**: الجدولُ لا يحمل `school_id` — مدرستُه تُشتقّ من جناحه. فسياستُه
مشتقّةٌ كسياسات `transport/0004`، ومسجَّلةٌ في `core/tenancy.py::PARENT_DERIVED`
كي لا يقع في العمى الذي وصفه صدرُ ذلك الملفّ.
"""

import django.contrib.postgres.constraints
import django.contrib.postgres.fields.ranges
import django.db.models.deletion
from django.conf import settings
from django.contrib.postgres.operations import BtreeGistExtension
from django.db import migrations, models

import core.models.academic
import core.models.school

TABLE = "core_wingcoverage"
CURRENT = "public.app_rls_school()"

#: مدرسةُ التغطية مدرسةُ جناحها — لا عمودَ ثانياً يُخالفه.
PREDICATE = f"""
EXISTS (
    SELECT 1
    FROM public.core_wing AS w
    WHERE w.id = {TABLE}.wing_id
      AND w.school_id = {CURRENT}
)
"""

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
        ("core", "0063_rls_wing"),
        ("core", "0037_rls_tenant_identity_from_db_role"),
    ]

    operations = [
        BtreeGistExtension(),
        migrations.CreateModel(
            name="WingCoverage",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=core.models.school._uuid,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                (
                    "reason",
                    models.CharField(
                        choices=[
                            ("absence", "غيابُ المشرف"),
                            ("leave", "إجازة"),
                            ("vacancy", "جناحٌ بلا مشرف"),
                            ("other", "أخرى"),
                        ],
                        default="absence",
                        max_length=10,
                    ),
                ),
                ("start_date", models.DateField(verbose_name="من")),
                ("end_date", models.DateField(blank=True, null=True, verbose_name="إلى")),
                ("note", models.TextField(blank=True, verbose_name="ملاحظة")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "assigned_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="wing_coverages_assigned",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="عيّنه",
                    ),
                ),
                (
                    "ended_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="wing_coverages_ended",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="أنهاها",
                    ),
                ),
                (
                    "substitute",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="wing_coverages",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="البديل",
                    ),
                ),
                (
                    "wing",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="coverages",
                        to="core.wing",
                    ),
                ),
            ],
            options={
                "verbose_name": "تغطيةُ جناح",
                "verbose_name_plural": "تغطياتُ الأجنحة",
                "ordering": ["-start_date"],
                "indexes": [
                    models.Index(
                        fields=["wing", "start_date"], name="core_wingco_wing_id_8985bd_idx"
                    )
                ],
                "constraints": [
                    models.CheckConstraint(
                        condition=models.Q(
                            ("end_date__isnull", True),
                            ("end_date__gte", models.F("start_date")),
                            _connector="OR",
                        ),
                        name="wing_coverage_ends_after_it_starts",
                    ),
                    django.contrib.postgres.constraints.ExclusionConstraint(
                        expressions=[
                            (
                                core.models.academic.DateRange(
                                    "start_date",
                                    "end_date",
                                    django.contrib.postgres.fields.ranges.RangeBoundary(
                                        inclusive_upper=True
                                    ),
                                ),
                                "&&",
                            ),
                            ("wing", "="),
                        ],
                        name="no_overlapping_wing_coverage",
                    ),
                ],
            },
        ),
        migrations.RunSQL(sql=ENABLE, reverse_sql=DISABLE),
    ]

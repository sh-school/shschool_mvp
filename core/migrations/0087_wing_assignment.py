"""سجلُّ تعيينات الأجنحة (مشرفٌ وميدانيّ) + دورُ التغطية — هجرةُ توسيعٍ (W-20261119-001).

`Wing.supervisor` يبقى حيّاً (حذفُه تقليصٌ لاحق)، وتُنسخ قيمتُه تعييناً مفتوحاً لدور المشرف
فتبدأ القراءةُ من السجلّ الزمنيّ بلا فجوة. والنسخُ idempotent: لا يكرّر تعييناً موجوداً.

وعزلُ الصفّ مشتقٌّ من الجناح كـ`WingCoverage` في `0064` (والجدولُ مسجَّلٌ في `core/tenancy.py`).
"""

import datetime

import django.contrib.postgres.constraints
import django.contrib.postgres.fields.ranges
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models

import core.models.academic
import core.models.school

TABLE = "core_wingassignment"
CURRENT = "public.app_rls_school()"

PREDICATE = f"""
EXISTS (
    SELECT 1
    FROM public.core_wing AS w
    WHERE w.id = {TABLE}.wing_id
      AND w.school_id = {CURRENT}
)
"""  # noqa: S608 — اسمُ الجدول ثابتٌ في الملفّ لا مُدخَلٌ

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


def _year_start(year: str) -> datetime.date:
    """أوّلُ سبتمبر من سنة العام الدراسيّ («2026-2027» ← 2026-09-01)."""
    try:
        return datetime.date(int(year[:4]), 9, 1)
    except (TypeError, ValueError):
        return datetime.date.today()


def copy_supervisors(apps, schema_editor):
    """ينسخ `Wing.supervisor` تعييناً مفتوحاً لدور المشرف — لأحدث عامٍ في كلّ مدرسةٍ وحدَه.

    فمشرفٌ واحدٌ في جناحين من عامين لا يتصادم مع قيد «الدورِ نفسِه في جناحين».
    """
    Wing = apps.get_model("core", "Wing")
    WingAssignment = apps.get_model("core", "WingAssignment")
    latest: dict = {}
    for school_id, year in Wing.objects.values_list("school_id", "academic_year"):
        if year > latest.get(school_id, ""):
            latest[school_id] = year
    for wing in Wing.objects.filter(is_active=True, supervisor__isnull=False):
        if wing.academic_year != latest.get(wing.school_id):
            continue
        WingAssignment.objects.get_or_create(
            wing=wing,
            role="wing_supervisor",
            user_id=wing.supervisor_id,
            defaults={"start_date": _year_start(wing.academic_year)},
        )


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0086_elective_group_membership"),
    ]

    operations = [
        migrations.AddField(
            model_name="wingcoverage",
            name="role",
            field=models.CharField(
                choices=[
                    ("wing_supervisor", "مشرف الجناح"),
                    ("field_supervisor", "المشرف الميداني"),
                ],
                default="wing_supervisor",
                max_length=20,
                verbose_name="الدور",
            ),
        ),
        migrations.CreateModel(
            name="WingAssignment",
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
                    "role",
                    models.CharField(
                        choices=[
                            ("wing_supervisor", "مشرف الجناح"),
                            ("field_supervisor", "المشرف الميداني"),
                        ],
                        max_length=20,
                        verbose_name="الدور",
                    ),
                ),
                ("start_date", models.DateField(verbose_name="من")),
                ("end_date", models.DateField(blank=True, null=True, verbose_name="إلى")),
                (
                    "created_at",
                    models.DateTimeField(auto_now_add=True, verbose_name="تاريخ الإنشاء"),
                ),
                (
                    "assigned_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="wing_assignments_made",
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
                        related_name="wing_assignments_ended",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="أنهاه",
                    ),
                ),
                (
                    "user",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="wing_assignments",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="المعيَّن",
                    ),
                ),
                (
                    "wing",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="assignments",
                        to="core.wing",
                        verbose_name="الجناح",
                    ),
                ),
            ],
            options={
                "verbose_name": "تعيينُ جناح",
                "verbose_name_plural": "تعيينات الأجنحة",
                "ordering": ["-start_date"],
                "indexes": [
                    models.Index(
                        fields=["wing", "role", "start_date"],
                        name="core_wingas_wing_role_idx",
                    )
                ],
                "constraints": [
                    models.CheckConstraint(
                        condition=models.Q(
                            ("end_date__isnull", True),
                            ("end_date__gte", models.F("start_date")),
                            _connector="OR",
                        ),
                        name="wing_assignment_ends_after_it_starts",
                    ),
                    *[
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
                                *[(field, "=") for field in fields],
                            ],
                            name=name,
                        )
                        for name, fields in (
                            ("no_overlapping_wing_assignment", ("wing", "role")),
                            ("no_user_same_role_in_two_wings", ("user", "role")),
                            ("no_user_two_roles_in_one_wing", ("user", "wing")),
                        )
                    ],
                ],
            },
        ),
        # النسخُ قبل تفعيل عزل الصفّ: الهجرةُ تكتب عبر المدارس، وسياسةُ الجدول تُقيّدها بمدرسةٍ واحدة.
        migrations.RunPython(copy_supervisors, migrations.RunPython.noop),
        migrations.RunSQL(sql=ENABLE, reverse_sql=DISABLE),
    ]

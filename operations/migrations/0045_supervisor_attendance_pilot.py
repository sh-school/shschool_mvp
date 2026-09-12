"""حقلا «أين الطالب» و«المصدر»، وسجلُّ تثبيت رصدِ الشعبة — ومعها عزلُ الصفّ.

`core/0037` فعّل RLS على كلّ جدولٍ يحمل `school_id` **يومَ كُتب**، وهي مطابقةٌ
لا تُعاد. فجدولٌ يُنشأ بعدها يخرج بلا عزلٍ ولا سياسة، والحارسان
`test_parent_derived_rls` و`test_rls_middleware` يسمّيانه فوراً. وقد وقع هذا
مع `core_wing` قبل يومٍ، فلا يُعاد.

و`operations_sectiondayconfirmation` يحمل `school_id` بنفسه، فالسياسةُ مباشرةٌ
لا مشتقّة.
"""

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models

import operations.models

TABLE = "operations_sectiondayconfirmation"
CURRENT = "public.app_rls_school()"
PREDICATE = f"{TABLE}.school_id = {CURRENT}"

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
        ("core", "0064_wing_coverage"),
        ("operations", "0044_swap_two_signatures_and_session_origin"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name="studentattendance",
            name="source",
            field=models.CharField(
                choices=[
                    ("teacher", "معلّم الحصّة"),
                    ("supervisor", "مشرف الجناح"),
                    ("gate", "ملاحظ الطلبة"),
                    ("clinic", "العيادة"),
                    ("system", "النظام"),
                ],
                db_index=True,
                default="teacher",
                max_length=12,
                verbose_name="المصدر",
            ),
        ),
        migrations.AddField(
            model_name="studentattendance",
            name="whereabouts",
            field=models.CharField(
                blank=True,
                choices=[
                    ("clinic", "في العيادة"),
                    ("activity", "في نشاطٍ مدرسيّ"),
                    ("out_permit", "خرج بإذن"),
                    ("out_no_permit", "خرج دون إذن"),
                    ("left_early", "استئذانٌ مبكّر"),
                    ("gate", "عند البوّابة (وصولٌ متأخّر)"),
                ],
                help_text="فارغٌ = في فصله. وما سواه سببُ غيابه عن الفصل لا عن المدرسة",
                max_length=14,
                verbose_name="مكانُ الطالب",
            ),
        ),
        migrations.CreateModel(
            name="SectionDayConfirmation",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=operations.models._uuid,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                ("date", models.DateField(db_index=True)),
                ("confirmed_at", models.DateTimeField(auto_now=True)),
                ("present_count", models.PositiveSmallIntegerField(default=0)),
                ("absent_count", models.PositiveSmallIntegerField(default=0)),
                ("late_count", models.PositiveSmallIntegerField(default=0)),
                ("periods_written", models.PositiveSmallIntegerField(default=0)),
                ("note", models.TextField(blank=True)),
                (
                    "class_group",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="day_confirmations",
                        to="core.classgroup",
                    ),
                ),
                (
                    "confirmed_by",
                    models.ForeignKey(
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="day_confirmations",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "school",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="day_confirmations",
                        to="core.school",
                    ),
                ),
            ],
            options={
                "verbose_name": "تثبيتُ رصدِ شعبة",
                "verbose_name_plural": "تثبيتاتُ رصد الشُّعب",
                "ordering": ["-date", "class_group"],
                "indexes": [
                    models.Index(fields=["school", "date"], name="operations__school__f8adf8_idx")
                ],
                "constraints": [
                    models.UniqueConstraint(
                        fields=("class_group", "date"), name="unique_section_day_confirmation"
                    )
                ],
            },
        ),
        migrations.RunSQL(sql=ENABLE, reverse_sql=DISABLE),
    ]

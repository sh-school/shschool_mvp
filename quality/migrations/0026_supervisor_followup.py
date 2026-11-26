"""جداولُ متابعة أداء المشرف الإداريّ (نموذج 19) وعزلُ صفوفها — هجرةُ توسيعٍ (W-20261125-003).

الجداولُ الثلاثةُ تحمل `school_id` فالسياسةُ مباشرة، وللابنين شرطٌ زائدٌ في `WITH CHECK`:
أن يكون الأبُ (و`reviewed_in`) من المدرسة نفسِها، لأنّ المفاتيحَ الأجنبيّة تُفحص خارج RLS.
"""

import uuid

import django.db.models.deletion
import django.utils.timezone
from django.conf import settings
from django.db import migrations, models

CURRENT = "public.app_rls_school()"
PARENT = "quality_supervisorfollowup"
SCORE = "quality_supervisorfollowupscore"
RECOMMENDATION = "quality_supervisorfollowuprecommendation"


def _parent_in_school(table, column):
    return f"""
    EXISTS (
        SELECT 1 FROM public.{PARENT} AS p
        WHERE p.id = {table}.{column} AND p.school_id = {table}.school_id
    )
    """  # noqa: S608 — أسماءُ جداولَ ثابتةٌ في الملفّ لا مُدخَل


def _enable(table, using, check):
    return f"""
ALTER TABLE public.{table} ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS school_isolation ON public.{table};

CREATE POLICY school_isolation ON public.{table}
    USING ({using})
    WITH CHECK ({check});
"""


def _disable(table):
    return f"""
DROP POLICY IF EXISTS school_isolation ON public.{table};
ALTER TABLE public.{table} DISABLE ROW LEVEL SECURITY;
"""


PARENT_USING = f"{PARENT}.school_id = {CURRENT}"
SCORE_USING = f"{SCORE}.school_id = {CURRENT}"
SCORE_CHECK = f"{SCORE_USING} AND {_parent_in_school(SCORE, 'followup_id')}"
RECOMMENDATION_USING = f"{RECOMMENDATION}.school_id = {CURRENT}"
RECOMMENDATION_CHECK = (
    f"{RECOMMENDATION_USING} AND {_parent_in_school(RECOMMENDATION, 'followup_id')}"
    f" AND ({RECOMMENDATION}.reviewed_in_id IS NULL"
    f" OR {_parent_in_school(RECOMMENDATION, 'reviewed_in_id')})"
)

STATUS = [("draft", "مسودة"), ("saved", "محفوظة")]
RATINGS = [
    ("complete", "مستكمل"),
    ("partial", "مستكمل جزئياً"),
    ("incomplete", "غير مستكمل"),
    ("not_measured", "لم يتم قياسه"),
]
REC_STATUS = [("pending", "لم تُتابع بعد"), ("done", "نُفّذ"), ("not_done", "لم يُنفّذ")]


def _id():
    return (
        "id",
        models.UUIDField(
            default=uuid.uuid4,
            editable=False,
            primary_key=True,
            serialize=False,
        ),
    )


def _audit_fields():
    # `related_name` يُكتب قالباً كما في `AuditedModel`، وإلا رآه كاشفُ الهجرات تغييراً.
    return [
        ("created_at", models.DateTimeField(auto_now_add=True, verbose_name="تاريخ الإنشاء")),
        ("updated_at", models.DateTimeField(auto_now=True, verbose_name="تاريخ التعديل")),
        (
            "created_by",
            models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="%(app_label)s_%(class)s_created",
                to=settings.AUTH_USER_MODEL,
                verbose_name="أنشأه",
            ),
        ),
        (
            "updated_by",
            models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="%(app_label)s_%(class)s_updated",
                to=settings.AUTH_USER_MODEL,
                verbose_name="عدّله",
            ),
        ),
    ]


def _soft_delete_fields():
    return [
        (
            "is_deleted",
            models.BooleanField(db_index=True, default=False, verbose_name="محذوف"),
        ),
        ("deleted_at", models.DateTimeField(blank=True, null=True, verbose_name="تاريخ الحذف")),
    ]


def _count(name, label):
    return (name, models.PositiveSmallIntegerField(default=0, verbose_name=label))


class Migration(migrations.Migration):
    dependencies = [
        ("quality", "0025_moe_plan_criterion_text"),
        ("core", "0037_rls_tenant_identity_from_db_role"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="SupervisorFollowUp",
            fields=[
                *_audit_fields(),
                *_soft_delete_fields(),
                _id(),
                (
                    "follow_date",
                    models.DateField(
                        default=django.utils.timezone.localdate, verbose_name="التاريخ"
                    ),
                ),
                (
                    "status",
                    models.CharField(
                        choices=STATUS, default="draft", max_length=10, verbose_name="الحالة"
                    ),
                ),
                ("strengths", models.TextField(blank=True, verbose_name="جوانب القوة")),
                (
                    "improvements",
                    models.TextField(blank=True, verbose_name="جوانب تحتاج إلى تحسين"),
                ),
                (
                    "period_start",
                    models.DateField(blank=True, null=True, verbose_name="بداية الفترة المحسوبة"),
                ),
                (
                    "period_end",
                    models.DateField(blank=True, null=True, verbose_name="نهاية الفترة المحسوبة"),
                ),
                _count("sick_days", "مرضي"),
                _count("casual_days", "عرضي"),
                _count("unpaid_days", "بلا راتب"),
                _count("permit_count", "الاستئذان"),
                _count("late_count", "التأخير الصباحي"),
                (
                    "school",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="supervisor_followups",
                        to="core.school",
                        verbose_name="المدرسة",
                    ),
                ),
                (
                    "supervisor",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="supervisor_followups_received",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="المشرف الإداري",
                    ),
                ),
                (
                    "follower",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="supervisor_followups_made",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="المتابِع",
                    ),
                ),
            ],
            options={
                "verbose_name": "متابعة مشرف إداري",
                "verbose_name_plural": "متابعات المشرفين الإداريين",
                "ordering": ["-follow_date", "-created_at"],
                "indexes": [
                    models.Index(
                        fields=["school", "supervisor", "follow_date"],
                        name="supfu_sup_date_idx",
                    )
                ],
                "constraints": [
                    models.UniqueConstraint(
                        condition=models.Q(("is_deleted", False), ("status", "draft")),
                        fields=("school", "supervisor"),
                        name="uniq_supfu_open_draft",
                    )
                ],
            },
        ),
        migrations.CreateModel(
            name="SupervisorFollowUpScore",
            fields=[
                *_audit_fields(),
                _id(),
                ("indicator_no", models.PositiveSmallIntegerField(verbose_name="رقم المؤشر")),
                (
                    "rating",
                    models.CharField(
                        blank=True, choices=RATINGS, max_length=15, verbose_name="التقدير"
                    ),
                ),
                ("note", models.TextField(blank=True, verbose_name="ملاحظات")),
                (
                    "school",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="+",
                        to="core.school",
                        verbose_name="المدرسة",
                    ),
                ),
                (
                    "followup",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="scores",
                        to="quality.supervisorfollowup",
                        verbose_name="المتابعة",
                    ),
                ),
            ],
            options={
                "verbose_name": "تقدير مؤشر متابعة",
                "verbose_name_plural": "تقديرات مؤشرات المتابعة",
                "ordering": ["indicator_no"],
                "constraints": [
                    models.UniqueConstraint(
                        fields=("followup", "indicator_no"), name="uniq_supfu_score"
                    )
                ],
            },
        ),
        migrations.CreateModel(
            name="SupervisorFollowUpRecommendation",
            fields=[
                *_audit_fields(),
                *_soft_delete_fields(),
                _id(),
                ("order", models.PositiveSmallIntegerField(default=0, verbose_name="الترتيب")),
                ("text", models.TextField(verbose_name="التوصية")),
                (
                    "status",
                    models.CharField(
                        choices=REC_STATUS,
                        default="pending",
                        max_length=10,
                        verbose_name="حالة التنفيذ",
                    ),
                ),
                ("note", models.TextField(blank=True, verbose_name="الملاحظات")),
                (
                    "school",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="+",
                        to="core.school",
                        verbose_name="المدرسة",
                    ),
                ),
                (
                    "followup",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="recommendations",
                        to="quality.supervisorfollowup",
                        verbose_name="المتابعة",
                    ),
                ),
                (
                    "reviewed_in",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="reviewed_recommendations",
                        to="quality.supervisorfollowup",
                        verbose_name="المتابعة التي تابعتها",
                    ),
                ),
            ],
            options={
                "verbose_name": "توصية متابعة",
                "verbose_name_plural": "توصيات المتابعة",
                "ordering": ["order", "created_at"],
            },
        ),
        migrations.RunSQL(
            sql=_enable(PARENT, PARENT_USING, PARENT_USING),
            reverse_sql=_disable(PARENT),
        ),
        migrations.RunSQL(
            sql=_enable(SCORE, SCORE_USING, SCORE_CHECK),
            reverse_sql=_disable(SCORE),
        ),
        migrations.RunSQL(
            sql=_enable(RECOMMENDATION, RECOMMENDATION_USING, RECOMMENDATION_CHECK),
            reverse_sql=_disable(RECOMMENDATION),
        ),
    ]

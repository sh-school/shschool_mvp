"""
مستوياتُ تقييم الأداء الخمسة بعتبات المادة 16، ووسمُ الفترتين.

المادة 16 من النظام الوظيفي لموظفي المدارس (قرار مجلس الوزراء 32/2019)،
«02- النظام الوظيفي لموظفي المدارس.pdf» صفحتا الملفّ 10–11: ممتاز 90 فأعلى،
جيد جداً أعلى من 75 إلى أقل من 90، جيد أعلى من 65 إلى 75، مقبول من 50 إلى 65،
ضعيف أقل من 50. وكانت المنصّةُ أربعَ درجاتٍ بعتبات 90/75/60 و«يحتاج تطوير».

الترحيلُ يعيد حسابَ `rating` لكلّ صفٍّ كما يحسبه النموذج (`EmployeeEvaluation.save`):
  - تقييمٌ على قالبٍ بدرجات مقيِّمين: من المجموع المرجَّح **غير المقرَّب** — لا من
    `total_score` المقرَّب، فـ89.5 المخزَّنُ 90 «جيد جداً» لا «ممتاز». ويُكتب `total_score`
    داخل نطاق مستواه (`EmployeeEvaluation.total_for`).
  - غيرُه: من `total_score` (العددُ الصحيح هو المجموعُ نفسُه).
  - مسودّةٌ فارغة (لا درجةَ ولا مقيِّم — ما كان GET القديم يُنشئه عند فتح النموذج):
    `rating` فارغ، لا «ضعيف». المستوى اسمٌ وزاريٌّ تترتّب عليه آثارُ المادتين 21 و22.
  - تقريرٌ سنويٌّ (S2) ليس على الاستمارة — بلا قالب، أو بلا درجاتِ مقيِّم، أو بمفاتيحَ غيرِ
    مفاتيح محاور قالبه (`EmployeeEvaluation.has_form_scores`): `rating` فارغ. فمستوياتُ المادة 16
    مستوياتُ التقرير الموضوع «وفقاً للنماذج المعتمدة من الوزير» (المادة 15، صفحة الملفّ 10).
وكلُّ صفٍّ يغيّره يُسجَّل قبلُ في `EvaluationLevelBackup` (المجموعُ والمستوى قبله وبعده).
وتكرارُه لا يغيّر شيئاً. وعكسُه يسترجع المسجَّلَ لكلّ صفٍّ لم يتغيّر منذ التقدّم، ويصنّف غيرَه
بالعتبات القديمة من `total_score`، ثمّ يحذف السجلّ.
"""

import math
from fractions import Fraction
from typing import Any

import django.db.models.deletion
from django.db import migrations, models

_AXES = ("axis_professional", "axis_commitment", "axis_teamwork", "axis_development")


def _five_levels(total: int | Fraction) -> str:
    if total >= 90:
        return "excellent"
    if total > 75:
        return "very_good"
    if total > 65:
        return "good"
    if total >= 50:
        return "acceptable"
    return "weak"


def _four_levels(total: int) -> str:
    if total >= 90:
        return "excellent"
    if total >= 75:
        return "very_good"
    if total >= 60:
        return "good"
    return "needs_dev"


def _weighted(evaluation: Any, score_model: Any) -> Fraction | None:
    """المجموعُ المرجَّح غير المقرَّب كما في `calculate_weighted_total`، أو None."""
    if evaluation.template_id is None:
        return None
    weighted = weight_sum = 0
    for score in score_model.objects.filter(evaluation_id=evaluation.pk):
        custom = score.custom_axes or {}
        total = sum(custom.values()) if custom else sum(getattr(score, f) for f in _AXES)
        weighted += total * score.weight
        weight_sum += score.weight
    return Fraction(weighted, weight_sum) if weight_sum else None


def _shown(exact: Fraction) -> int:
    """`EmployeeEvaluation.total_for`: الأقربُ داخل نطاق المستوى."""
    rounded = round(exact)
    if _five_levels(rounded) == _five_levels(exact):
        return int(rounded)
    return math.floor(exact) if rounded > exact else math.ceil(exact)


def _is_blank(evaluation: Any, score_model: Any) -> bool:
    return (
        evaluation.status == "draft"
        and not evaluation.total_score
        and not any(getattr(evaluation, f) for f in _AXES)
        and not score_model.objects.filter(evaluation_id=evaluation.pk).exists()
    )


def _off_form(evaluation: Any, score_model: Any, axis_model: Any) -> bool:
    """تقريرٌ سنويٌّ ليس على الاستمارة — كما `EmployeeEvaluation.has_form_scores` معكوساً."""
    if evaluation.period != "S2":
        return False
    if evaluation.template_id is None:
        return True
    keys = set(
        axis_model.objects.filter(template_id=evaluation.template_id).values_list("key", flat=True)
    )
    rows = [
        set(custom or {})
        for custom in score_model.objects.filter(evaluation_id=evaluation.pk).values_list(
            "custom_axes", flat=True
        )
    ]
    return not (keys and rows and all(row == keys for row in rows))


def forward(apps: Any, schema_editor: Any) -> None:
    EmployeeEvaluation = apps.get_model("quality", "EmployeeEvaluation")
    EvaluationScore = apps.get_model("quality", "EvaluationScore")
    EvaluationAxis = apps.get_model("quality", "EvaluationAxis")
    EvaluationLevelBackup = apps.get_model("quality", "EvaluationLevelBackup")
    for ev in EmployeeEvaluation.objects.all().iterator():
        total = ev.total_score
        if _is_blank(ev, EvaluationScore):
            rating = ""
        else:
            exact = _weighted(ev, EvaluationScore)
            if exact is not None:
                total = _shown(exact)
            rating = _five_levels(exact if exact is not None else total)
            if _off_form(ev, EvaluationScore, EvaluationAxis):
                rating = ""
        if (total, rating) != (ev.total_score, ev.rating):
            # يُسجَّل ما كان قبل أن يُكتب فوقه (`EvaluationLevelBackup`): فالعكسُ يسترجعه، ولا
            # يفقد تقريرٌ مُقَرٌّ به مستواه بلا أثر. وفي تكرار التقدّم يبقى «قبل» أوّلَ ما سُجّل.
            backup, created = EvaluationLevelBackup.objects.get_or_create(
                evaluation_id=ev.pk,
                defaults={
                    "old_total_score": ev.total_score,
                    "old_rating": ev.rating,
                    "new_total_score": total,
                    "new_rating": rating,
                },
            )
            if not created:
                backup.new_total_score, backup.new_rating = total, rating
                backup.save(update_fields=["new_total_score", "new_rating"])
            EmployeeEvaluation.objects.filter(pk=ev.pk).update(total_score=total, rating=rating)


def backward(apps: Any, schema_editor: Any) -> None:
    """
    ما غيّره التقدّمُ يعود كما سُجِّل — ما لم يتغيّر الصفُّ بعده، فيُصنَّف بالعتبات القديمة
    كغيره. والمستوى الفارغُ يبقى فارغاً: لا يُخترع مستوىً لمسودّةٍ أو لتقريرٍ لم يكن له.
    """
    EmployeeEvaluation = apps.get_model("quality", "EmployeeEvaluation")
    EvaluationLevelBackup = apps.get_model("quality", "EvaluationLevelBackup")
    restored: set[int] = set()
    for backup in EvaluationLevelBackup.objects.all().iterator():
        if EmployeeEvaluation.objects.filter(
            pk=backup.evaluation_id,
            total_score=backup.new_total_score,
            rating=backup.new_rating,
        ).update(total_score=backup.old_total_score, rating=backup.old_rating):
            restored.add(backup.evaluation_id)
    EvaluationLevelBackup.objects.all().delete()
    rows = EmployeeEvaluation.objects.exclude(rating="").exclude(pk__in=restored)
    for ev in rows.only("pk", "total_score", "rating").iterator():
        new = _four_levels(ev.total_score)
        if new != ev.rating:
            EmployeeEvaluation.objects.filter(pk=ev.pk).update(rating=new)


# ── عزلُ السجلّ: مجموعُ كلّ موظّفٍ ومستواه قبل الهجرة وبعدها بياناتُ أداءٍ شخصيّة ──────────
# لا `school_id` فيه، فمدرستُه مدرسةُ تقريره — كسياسة `quality_evaluationscore`
# (`0015_rls_parent_derived`)، ومسجَّلٌ في `core/tenancy.py::PARENT_DERIVED`.
BACKUP = "quality_evaluationlevelbackup"
CURRENT = "public.app_rls_school()"
BACKUP_PREDICATE = f"""
EXISTS (
    SELECT 1
    FROM public.quality_employeeevaluation AS evaluation
    WHERE evaluation.id = {BACKUP}.evaluation_id
      AND evaluation.school_id = {CURRENT}
)
"""  # noqa: S608 — ثوابتُ أسماءِ جداول، لا مدخلاتٌ من مستخدم
BACKUP_RLS = f"""
ALTER TABLE public.{BACKUP} ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS school_isolation ON public.{BACKUP};

CREATE POLICY school_isolation ON public.{BACKUP}
    USING ({BACKUP_PREDICATE})
    WITH CHECK ({BACKUP_PREDICATE});
"""
BACKUP_RLS_REVERSE = f"""
DROP POLICY IF EXISTS school_isolation ON public.{BACKUP};
ALTER TABLE public.{BACKUP} DISABLE ROW LEVEL SECURITY;
"""

PERIODS = [
    ("S1", "متابعة منتصف العام (داخليّة، غير وزاريّة)"),
    ("S2", "التقرير السنويّ (الوزاريّ)"),
]


class Migration(migrations.Migration):
    dependencies = [
        ("quality", "0017_alter_classroomobservation_kind"),
        ("core", "0037_rls_tenant_identity_from_db_role"),
    ]

    operations = [
        migrations.AlterField(
            model_name="employeeevaluation",
            name="rating",
            field=models.CharField(
                blank=True,
                choices=[
                    ("excellent", "ممتاز (100–90)"),
                    ("very_good", "جيد جداً (89–76)"),
                    ("good", "جيد (75–66)"),
                    ("acceptable", "مقبول (65–50)"),
                    ("weak", "ضعيف (أقل من 50)"),
                ],
                max_length=15,
            ),
        ),
        migrations.AlterField(
            model_name="employeeevaluation",
            name="period",
            field=models.CharField(choices=PERIODS, max_length=2, verbose_name="الفترة"),
        ),
        migrations.AlterField(
            model_name="evaluationcycle",
            name="period",
            field=models.CharField(choices=PERIODS, max_length=2),
        ),
        migrations.CreateModel(
            name="EvaluationLevelBackup",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True, primary_key=True, serialize=False, verbose_name="ID"
                    ),
                ),
                (
                    "old_total_score",
                    models.PositiveSmallIntegerField(verbose_name="المجموع قبل الهجرة"),
                ),
                (
                    "old_rating",
                    models.CharField(blank=True, max_length=15, verbose_name="المستوى قبل الهجرة"),
                ),
                (
                    "new_total_score",
                    models.PositiveSmallIntegerField(verbose_name="المجموع بعد الهجرة"),
                ),
                (
                    "new_rating",
                    models.CharField(blank=True, max_length=15, verbose_name="المستوى بعد الهجرة"),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "evaluation",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="+",
                        to="quality.employeeevaluation",
                        verbose_name="التقييم",
                    ),
                ),
            ],
            options={
                "verbose_name": "مستوى تقييمٍ قبل الهجرة 0018",
                "verbose_name_plural": "مستويات التقييم قبل الهجرة 0018",
            },
        ),
        migrations.RunSQL(sql=BACKUP_RLS, reverse_sql=BACKUP_RLS_REVERSE),
        migrations.RunPython(forward, backward),
    ]

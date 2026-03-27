"""
Migration 0007 — إعادة هيكلة الباقات التقييمية حسب مواصفات وزارة التعليم القطرية.

التغييرات:
  1. إعادة تسمية package_type في AssessmentPackage:
       P3+S1 → P1  (منتصف الفصل الأول)
       P4+S1 → P2  (نهاية الفصل الأول)
       P3+S2 → P3  (بقيت كما هي — منتصف الفصل الثاني)
       P4+S2 → P4  (بقيت كما هي — نهاية الفصل الثاني)
       P1+any → AW  (أعمال مستمرة)
       P2+any → AW  (اختبارات قصيرة → دُمجت مع الأعمال)

  2. إضافة حقل p_aw_score في StudentSubjectResult.

  3. نقل بيانات p1_score القديمة → p_aw_score.
"""
from decimal import Decimal

from django.db import migrations, models


def migrate_package_types_forward(apps, schema_editor):
    """إعادة تسمية package_type لتطابق الهيكل الجديد.

    الترتيب مهم — يجب تحويل P1/P2 القديمة إلى AW أولاً
    قبل استخدام P1/P2 كأسماء جديدة للباقات.
    """
    AssessmentPackage = apps.get_model("assessments", "AssessmentPackage")

    # الخطوة 1: P1 القديمة (أعمال مستمرة) → AW  أولاً لتحرير الاسم P1
    AssessmentPackage.objects.filter(package_type="P1").update(package_type="AW")

    # الخطوة 2: P2 القديمة (اختبارات قصيرة) → AW  (دمج)
    AssessmentPackage.objects.filter(package_type="P2").update(package_type="AW")

    # الخطوة 3: الآن P1 و P2 متحررتان — نُعيد تسمية الباقات الدراسية
    # P3 + S1 → P1  (منتصف الفصل الأول)
    AssessmentPackage.objects.filter(package_type="P3", semester="S1").update(
        package_type="P1", weight=Decimal("37.50")
    )

    # P4 + S1 → P2  (نهاية الفصل الأول)
    AssessmentPackage.objects.filter(package_type="P4", semester="S1").update(
        package_type="P2", weight=Decimal("50.00")
    )

    # P3 + S2 تبقى P3، نصحح الوزن
    AssessmentPackage.objects.filter(package_type="P3", semester="S2").update(
        weight=Decimal("25.00")
    )

    # P4 + S2 تبقى P4، نصحح الوزن
    AssessmentPackage.objects.filter(package_type="P4", semester="S2").update(
        weight=Decimal("66.67")
    )

    # الخطوة 4: تصحيح أوزان AW لكل فصل
    AssessmentPackage.objects.filter(package_type="AW", semester="S1").update(
        weight=Decimal("12.50")
    )
    AssessmentPackage.objects.filter(package_type="AW", semester="S2").update(
        weight=Decimal("8.33")
    )


def migrate_package_types_backward(apps, schema_editor):
    """عكس العملية — إرجاع package_type إلى الهيكل القديم."""
    AssessmentPackage = apps.get_model("assessments", "AssessmentPackage")

    # P1 + S1 → P3
    AssessmentPackage.objects.filter(package_type="P1", semester="S1").update(
        package_type="P3", weight=Decimal("37.50")
    )
    # P2 + S1 → P4
    AssessmentPackage.objects.filter(package_type="P2", semester="S1").update(
        package_type="P4", weight=Decimal("50.00")
    )
    # AW → P1
    AssessmentPackage.objects.filter(package_type="AW").update(
        package_type="P1"
    )


def migrate_aw_scores_forward(apps, schema_editor):
    """نقل p1_score القديمة (أعمال مستمرة) إلى p_aw_score."""
    StudentSubjectResult = apps.get_model("assessments", "StudentSubjectResult")
    for r in StudentSubjectResult.objects.filter(p1_score__isnull=False):
        r.p_aw_score = r.p1_score
        r.p1_score = None
        r.save(update_fields=["p_aw_score", "p1_score"])


def migrate_aw_scores_backward(apps, schema_editor):
    """إرجاع p_aw_score إلى p1_score."""
    StudentSubjectResult = apps.get_model("assessments", "StudentSubjectResult")
    for r in StudentSubjectResult.objects.filter(p_aw_score__isnull=False):
        r.p1_score = r.p_aw_score
        r.p_aw_score = None
        r.save(update_fields=["p1_score", "p_aw_score"])


class Migration(migrations.Migration):

    dependencies = [
        ("assessments", "0006_update_package_weights"),
    ]

    operations = [
        # 1. إضافة حقل p_aw_score
        migrations.AddField(
            model_name="studentsubjectresult",
            name="p_aw_score",
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                max_digits=5,
                null=True,
                verbose_name="درجة الأعمال المستمرة",
            ),
        ),
        # 2. تحديث choices في package_type (لا يغير DB فعلياً، فقط metadata)
        migrations.AlterField(
            model_name="assessmentpackage",
            name="package_type",
            field=models.CharField(
                choices=[
                    ("P1", "الباقة الأولى — منتصف الفصل الأول"),
                    ("P2", "الباقة الثانية — نهاية الفصل الأول"),
                    ("P3", "الباقة الثالثة — منتصف الفصل الثاني"),
                    ("P4", "الباقة الرابعة — نهاية الفصل الثاني"),
                    ("AW", "أعمال مستمرة"),
                ],
                max_length=2,
                verbose_name="نوع الباقة",
            ),
        ),
        # 3. تحديث verbose_name لحقول p1–p4
        migrations.AlterField(
            model_name="studentsubjectresult",
            name="p1_score",
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                max_digits=5,
                null=True,
                verbose_name="درجة P1 — منتصف ف1",
            ),
        ),
        migrations.AlterField(
            model_name="studentsubjectresult",
            name="p2_score",
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                max_digits=5,
                null=True,
                verbose_name="درجة P2 — نهاية ف1",
            ),
        ),
        migrations.AlterField(
            model_name="studentsubjectresult",
            name="p3_score",
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                max_digits=5,
                null=True,
                verbose_name="درجة P3 — منتصف ف2",
            ),
        ),
        migrations.AlterField(
            model_name="studentsubjectresult",
            name="p4_score",
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                max_digits=5,
                null=True,
                verbose_name="درجة P4 — نهاية ف2",
            ),
        ),
        # 4. Data migrations
        migrations.RunPython(
            migrate_package_types_forward,
            migrate_package_types_backward,
        ),
        migrations.RunPython(
            migrate_aw_scores_forward,
            migrate_aw_scores_backward,
        ),
    ]

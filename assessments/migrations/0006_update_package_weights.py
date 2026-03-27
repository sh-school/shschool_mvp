"""
assessments/migrations/0006_update_package_weights.py

Data migration — تصحيح أوزان AssessmentPackage وpass_grade في AnnualSubjectResult
لتتوافق مع مواصفات وزارة التعليم القطرية.

الأوزان الصحيحة (نسبة % من مجموع الفصل):
  الفصل الأول  (semester_max=40):
    P1 أعمال مستمرة  =  12.50%  → 2  درجة من 40
    P2 اختبارات قصيرة=   0.00%  (غير مستخدم)
    P3 منتصف الفصل   =  37.50%  → 6  درجات من 40
    P4 نهاية الفصل   =  50.00%  → 8  درجات من 40

  الفصل الثاني (semester_max=60):
    P1 أعمال مستمرة  =   8.33%  → 3  درجات من 60
    P2 اختبارات قصيرة=   0.00%  (غير مستخدم)
    P3 منتصف الفصل   =  25.00%  → 9  درجات من 60
    P4 نهاية العام   =  66.67%  → 24 درجة  من 60
"""

from decimal import Decimal

from django.db import migrations


# الأوزان الصحيحة — مرآة لـ DEFAULT_WEIGHTS_S1 / DEFAULT_WEIGHTS_S2 في النموذج
CORRECT_WEIGHTS = {
    "S1": {
        "P1": Decimal("12.50"),
        "P2": Decimal("0.00"),
        "P3": Decimal("37.50"),
        "P4": Decimal("50.00"),
    },
    "S2": {
        "P1": Decimal("8.33"),
        "P2": Decimal("0.00"),
        "P3": Decimal("25.00"),
        "P4": Decimal("66.67"),
    },
}

# الدرجة القصوى الصحيحة لكل فصل
CORRECT_SEMESTER_MAX = {
    "S1": Decimal("40"),
    "S2": Decimal("60"),
}


def update_package_weights(apps, schema_editor):
    """تحديث AssessmentPackage.weight وsemester_max_grade للأوزان الصحيحة."""
    AssessmentPackage = apps.get_model("assessments", "AssessmentPackage")

    updated = 0
    for semester, type_weights in CORRECT_WEIGHTS.items():
        for pkg_type, correct_weight in type_weights.items():
            correct_max = CORRECT_SEMESTER_MAX[semester]
            count = AssessmentPackage.objects.filter(
                semester=semester,
                package_type=pkg_type,
            ).exclude(
                weight=correct_weight,
                semester_max_grade=correct_max,
            ).update(
                weight=correct_weight,
                semester_max_grade=correct_max,
            )
            updated += count

    print(f"  ✓ تم تحديث {updated} باقة تقييمية بالأوزان الصحيحة.")


def update_pass_grades(apps, schema_editor):
    """تحديث AnnualSubjectResult.pass_grade من 50 → 60."""
    AnnualSubjectResult = apps.get_model("assessments", "AnnualSubjectResult")

    count = AnnualSubjectResult.objects.filter(
        pass_grade=Decimal("50"),
    ).update(
        pass_grade=Decimal("60"),
    )

    print(f"  ✓ تم تحديث {count} نتيجة سنوية: pass_grade 50 → 60.")


def reverse_package_weights(apps, schema_editor):
    """لا تراجع حقيقي — عكس التحديث غير منطقي للبيانات الإنتاجية."""
    pass


def reverse_pass_grades(apps, schema_editor):
    """لا تراجع حقيقي — عكس التحديث غير منطقي للبيانات الإنتاجية."""
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("assessments", "0005_alter_annualsubjectresult_pass_grade"),
    ]

    operations = [
        migrations.RunPython(update_package_weights, reverse_package_weights),
        migrations.RunPython(update_pass_grades, reverse_pass_grades),
    ]

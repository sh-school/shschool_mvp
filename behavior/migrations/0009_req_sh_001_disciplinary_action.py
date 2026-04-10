# Generated manually for REQ-SH-001 — Client #001 (Shahaniya School, MTG-007)
# Adds structured disciplinary action dropdown + conditional violation description fields.
# Backward compatible: action_taken (legacy free-text) preserved.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("behavior", "0008_add_performance_indexes"),
    ]

    operations = [
        migrations.AddField(
            model_name="behaviorinfraction",
            name="disciplinary_action_type",
            field=models.CharField(
                blank=True,
                choices=[
                    ("verbal_warning", "تنبيه شفهي"),
                    ("written_pledge", "تعهد خطي"),
                    ("incident_report", "محضر لإثبات المخالفة"),
                    ("parent_pledge", "تعهد خطي لولي الأمر"),
                    ("social_specialist_referral", "تحويل للأخصائي الاجتماعي"),
                    ("parent_summons", "استدعاء ولي الأمر"),
                ],
                default="",
                help_text="الإجراء التأديبي الرسمي وفق لائحة المدرسة",
                max_length=50,
                verbose_name="الإجراء التأديبي",
            ),
        ),
        migrations.AddField(
            model_name="behaviorinfraction",
            name="violation_description",
            field=models.TextField(
                blank=True,
                default="",
                help_text="مطلوب فقط عند اختيار 'محضر لإثبات المخالفة' (20-2000 حرف)",
                max_length=2000,
                verbose_name="وصف المخالفة (محضر)",
            ),
        ),
    ]

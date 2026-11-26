"""إرسالُ متابعة المشرف وإقرارُه: حالتان وثلاثةُ حقول — هجرةُ توسيعٍ (W-20261125-008)."""

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("quality", "0026_supervisor_followup")]

    operations = [
        migrations.AddField(
            model_name="supervisorfollowup",
            name="sent_at",
            field=models.DateTimeField(blank=True, null=True, verbose_name="تاريخ الإرسال"),
        ),
        migrations.AddField(
            model_name="supervisorfollowup",
            name="acknowledged_at",
            field=models.DateTimeField(blank=True, null=True, verbose_name="تاريخ الإقرار"),
        ),
        migrations.AddField(
            model_name="supervisorfollowup",
            name="supervisor_comment",
            field=models.TextField(
                blank=True, db_default="", default="", verbose_name="تعليق المشرف"
            ),
        ),
        migrations.AlterField(
            model_name="supervisorfollowup",
            name="status",
            field=models.CharField(
                choices=[
                    ("draft", "مسودة"),
                    ("saved", "محفوظة"),
                    ("sent", "مُرسلة"),
                    ("acknowledged", "أُقرّت"),
                ],
                default="draft",
                max_length=15,
                verbose_name="الحالة",
            ),
        ),
    ]

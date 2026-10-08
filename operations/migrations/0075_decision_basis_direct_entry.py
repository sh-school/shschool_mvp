"""أساسُ قرارٍ جديد `direct_entry` — رصدٌ نهائيٌّ مباشرٌ بلا اعتماد لأجنحةٍ يحدّدها المالك (قرارُ 2026-10-07). قائمةُ اختيارٍ بلا SQL."""

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("operations", "0074_absence_alert_held_status"),
    ]

    operations = [
        migrations.AlterField(
            model_name="attendancedecision",
            name="basis",
            field=models.CharField(
                choices=[
                    ("wing_holder", "حاملُ جناح الشعبة"),
                    ("leadership_no_holder", "القيادةُ — لا حاملَ للجناح"),
                    (
                        "leadership_holder_is_teacher",
                        "القيادةُ — حاملُ الجناح هو معلّمُ الحصّة",
                    ),
                    (
                        "leadership_holder_inactive",
                        "القيادةُ — حاملُ الجناح بلا عضويّةٍ نشطة",
                    ),
                    ("school_wide", "حاصرُ الغياب العامّ — اعتمادٌ ثانٍ بجانب الحامل"),
                    ("supervisor_record", "كُتب رصدُ مشرفٍ فوق الإدخال"),
                    ("special_ed_self", "التربيةُ الخاصّة — اعتمادٌ ذاتيٌّ بالتصميم"),
                    (
                        "wing_holder_self",
                        "حاملُ الجناح — اعتمادُ ما كتبه بنفسه (جدولُ الشعبة)",
                    ),
                    (
                        "direct_entry",
                        "رصدٌ نهائيٌّ مباشر — جناحٌ بلا اعتماد (جدولُ الشعبة)",
                    ),
                ],
                max_length=40,
                verbose_name="أساسُ الصلاحيّة",
            ),
        ),
    ]

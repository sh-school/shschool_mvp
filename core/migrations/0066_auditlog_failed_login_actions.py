"""فشلُ الدخول وفشلُ رمز التحقّق يُدقَّقان.

كان `AuditLog` يسجّل الدخولَ الناجحَ والخروجَ، ولا يسجّل الفشل: عشرُ محاولاتٍ
خاطئةٍ على حسابِ المدير في دقيقةٍ لا يراها أحدٌ إلّا عدّادَ القفل في ذاكرة
الخادم، وهو يُصفَّر بأوّل نجاح. فأُضيف فعلان — `login_failed` و`mfa_failed` —
وطولُ الحقل من عشرةٍ إلى عشرين لأنّ `login_failed` اثنا عشرَ حرفاً.

هجرةُ خياراتٍ وطولٍ لا بيانات: ما في الجدول يبقى كما هو.
"""

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0065_role_support_companion"),
    ]

    operations = [
        migrations.AlterField(
            model_name="auditlog",
            name="action",
            field=models.CharField(
                choices=[
                    ("create", "إنشاء"),
                    ("update", "تعديل"),
                    ("delete", "حذف"),
                    ("view", "عرض"),
                    ("export", "تصدير"),
                    ("login", "تسجيل دخول"),
                    ("logout", "تسجيل خروج"),
                    ("login_failed", "محاولة دخول فاشلة"),
                    ("mfa_failed", "رمز تحقّق خاطئ"),
                ],
                max_length=20,
            ),
        ),
    ]

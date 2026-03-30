"""
Migration 0030 — إضافة 7 أدوار جديدة (v7)
══════════════════════════════════════════════════════════════════════
المرجع القانوني:
  - قرار مجلس الوزراء 32/2019 (النظام الوظيفي للمدارس) + تعديل 23/2025
  - إعلانات التوظيف الرسمية لوزارة التعليم 2022-2026

الأدوار المضافة:
  1. activities_coordinator — منسق الأنشطة المدرسية  (T3)
  2. teacher_assistant      — مساعد المعلم            (T4)  نص صريح قرار 32/2019
  3. ese_assistant          — مساعد معلم تربية خاصة  (T4)  نص صريح قرار 32/2019
  4. speech_therapist       — أخصائي النطق            (T4)  إعلان رسمي
  5. occupational_therapist — أخصائي العلاج الوظائفي (T4)  إعلان رسمي
  6. receptionist           — موظف استقبال            (T4)
  7. transport_officer      — مسؤول النقل             (T4)  مختلف عن مشرف الحافلة
══════════════════════════════════════════════════════════════════════
"""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0029_remove_membership_department"),
    ]

    operations = [
        migrations.AlterField(
            model_name="role",
            name="name",
            field=models.CharField(
                max_length=30,
                verbose_name="الدور الوظيفي",
                choices=[
                    # T1 — القيادة العليا
                    ("principal", "مدير المدرسة"),
                    # T2 — نواب المدير
                    ("vice_admin", "النائب الإداري"),
                    ("vice_academic", "النائب الأكاديمي"),
                    # T3 — المنسقون والإشراف
                    ("coordinator", "منسق أكاديمي"),
                    ("admin_supervisor", "مشرف إداري"),
                    ("activities_coordinator", "منسق الأنشطة المدرسية"),
                    # T4 — الكادر التدريسي
                    ("teacher", "معلم"),
                    ("ese_teacher", "معلم تربية خاصة"),
                    ("teacher_assistant", "مساعد المعلم"),
                    ("ese_assistant", "مساعد معلم تربية خاصة"),
                    # T4 — الدعم الأكاديمي والطلابي
                    ("social_worker", "أخصائي اجتماعي"),
                    ("psychologist", "أخصائي نفسي"),
                    ("academic_advisor", "مرشد أكاديمي"),
                    ("speech_therapist", "أخصائي النطق"),
                    ("occupational_therapist", "أخصائي العلاج الوظائفي"),
                    # T4 — الخدمات المساندة
                    ("nurse", "ممرض"),
                    ("librarian", "أمين مصادر التعلم"),
                    ("it_technician", "فني تقنية معلومات"),
                    ("bus_supervisor", "مشرف نقل مدرسي"),
                    ("transport_officer", "مسؤول النقل"),
                    # T4 — الإداريون
                    ("admin", "إداري"),
                    ("secretary", "سكرتير المدرسة"),
                    ("receptionist", "موظف استقبال"),
                    # T4-legacy
                    ("specialist", "أخصائي (قديم)"),
                    # T5 — المستفيدون
                    ("student", "طالب"),
                    ("parent", "ولي أمر"),
                    # System
                    ("platform_developer", "مطور المنصة"),
                ],
            ),
        ),
    ]

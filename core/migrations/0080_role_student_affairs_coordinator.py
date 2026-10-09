"""دورٌ باسمه لمنسّق شؤون الطلبة — W-20261001-020.

هجرةُ **خيارات** لا بيانات (توسيعٌ لا حذف): لا يتغيّر دورُ أحدٍ بها. سندُ الدور: بطاقتُه في
`03_job_descriptions_rbac.md` («إدخال بيانات الطلبة إلكترونياً وتحديثها») وم5.7 من سياسة السلوك.
"""

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0079_capability_grant_wings_school_wide"),
    ]

    operations = [
        migrations.AlterField(
            model_name="role",
            name="name",
            field=models.CharField(
                choices=[
                    ("principal", "مدير المدرسة"),
                    ("vice_admin", "النائب الإداري"),
                    ("vice_academic", "النائب الأكاديمي"),
                    ("coordinator", "منسق أكاديمي"),
                    ("admin_supervisor", "مشرف إداري"),
                    ("activities_coordinator", "منسق الأنشطة المدرسية"),
                    ("e_projects_coordinator", "منسق المشاريع الإلكترونية"),
                    ("student_affairs_coordinator", "منسق شؤون الطلبة"),
                    ("teacher", "معلم"),
                    ("ese_teacher", "معلم تربية خاصة"),
                    ("teacher_assistant", "مساعد المعلم"),
                    ("ese_assistant", "مساعد معلم تربية خاصة"),
                    ("social_worker", "أخصائي اجتماعي"),
                    ("psychologist", "أخصائي نفسي"),
                    ("academic_advisor", "مرشد أكاديمي"),
                    ("speech_therapist", "أخصائي النطق"),
                    ("occupational_therapist", "أخصائي العلاج الوظائفي"),
                    ("support_companion", "مرافق الدعم"),
                    ("nurse", "ممرض"),
                    ("librarian", "أمين مصادر التعلم"),
                    ("it_technician", "فني تقنية معلومات"),
                    ("bus_supervisor", "مشرف نقل مدرسي"),
                    ("transport_officer", "مسؤول النقل"),
                    ("admin", "إداري"),
                    ("secretary", "سكرتير المدرسة"),
                    ("receptionist", "موظف استقبال"),
                    ("student_observer", "ملاحظ طلبة"),
                    ("lab_technician", "محضّر مختبر"),
                    ("storekeeper", "أمين مخزن"),
                    ("accountant", "محاسب"),
                    ("canteen_supervisor", "مشرف مقصف"),
                    ("services_worker", "عامل خدمات"),
                    ("messenger", "مندوب"),
                    ("specialist", "أخصائي (قديم)"),
                    ("student", "طالب"),
                    ("parent", "ولي أمر"),
                    ("platform_developer", "مطور المنصة"),
                ],
                max_length=30,
                verbose_name="اسم الدور",
            ),
        ),
    ]

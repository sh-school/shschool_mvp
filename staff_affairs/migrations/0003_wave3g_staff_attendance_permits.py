# Generated migration for Wave 3G - Staff Attendance & Permits

from django.db import migrations, models
import django.db.models.deletion
from core.academic_calendar import default_academic_year


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0066_auditlog_failed_login_actions"),
        ("staff_affairs", "0002_alter_leavebalance_academic_year_and_more"),
    ]

    operations = [
        # 1.1: StaffAttendance model
        migrations.CreateModel(
            name="StaffAttendance",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True, verbose_name="تاريخ الإنشاء")),
                ("updated_at", models.DateTimeField(auto_now=True, verbose_name="تاريخ التحديث")),
                ("date", models.DateField(db_index=True, verbose_name="التاريخ")),
                ("check_in_time", models.TimeField(blank=True, null=True, verbose_name="وقتُ الحضور")),
                ("check_out_time", models.TimeField(blank=True, null=True, verbose_name="وقتُ الانصراف")),
                ("permit_minutes", models.PositiveSmallIntegerField(default=0, verbose_name="دقائقُ الاستئذانِ المقبول")),
                ("status", models.CharField(
                    choices=[("present", "حاضر"), ("late", "متأخّر"), ("absent", "غائب")],
                    db_index=True,
                    max_length=10,
                    verbose_name="الحالة",
                )),
                ("notes", models.TextField(blank=True, verbose_name="ملاحظات")),
                ("school", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to="core.school")),
                ("staff", models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="staff_attendances",
                    to="core.customuser",
                    verbose_name="الموظّف",
                )),
            ],
            options={
                "verbose_name": "حضورُ موظّف",
                "verbose_name_plural": "حضورُ الموظّفين",
                "ordering": ["-date"],
            },
        ),
        migrations.AddIndex(
            model_name="staffattendance",
            index=models.Index(fields=["school", "staff", "date"], name="staff_aff_school_1234567890_idx"),
        ),
        migrations.AddIndex(
            model_name="staffattendance",
            index=models.Index(fields=["school", "date", "status"], name="staff_aff_date_st_idx"),
        ),
        migrations.AddConstraint(
            model_name="staffattendance",
            constraint=models.UniqueConstraint(fields=["school", "staff", "date"], name="unique_staff_attendance_per_day"),
        ),

        # 1.3: PermitRequest model
        migrations.CreateModel(
            name="PermitRequest",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True, verbose_name="تاريخ الإنشاء")),
                ("updated_at", models.DateTimeField(auto_now=True, verbose_name="تاريخ التحديث")),
                ("created_by_id", models.IntegerField(null=True, blank=True)),
                ("updated_by_id", models.IntegerField(null=True, blank=True)),
                ("permit_type", models.CharField(
                    choices=[
                        ("late_arrival", "تأخيرٌ صباحيّ"),
                        ("early_departure", "خروجٌ مبكّر"),
                        ("permit", "استئذانٌ أثناء الدوام"),
                    ],
                    max_length=20,
                    verbose_name="نوعُ الإذن",
                )),
                ("date", models.DateField(verbose_name="التاريخ")),
                ("start_time", models.TimeField(verbose_name="بدايةُ الفترة")),
                ("end_time", models.TimeField(verbose_name="نهايةُ الفترة")),
                ("duration_minutes", models.PositiveSmallIntegerField(editable=False, verbose_name="المدّةُ بالدقائق")),
                ("reason", models.TextField(max_length=1000, verbose_name="السبب")),
                ("status", models.CharField(
                    choices=[
                        ("pending", "قيدُ الانتظار"),
                        ("approved", "مقبولٌ"),
                        ("rejected", "مرفوضٌ"),
                        ("cancelled", "ملغىً"),
                    ],
                    db_index=True,
                    default="pending",
                    max_length=15,
                    verbose_name="الحالة",
                )),
                ("reviewed_at", models.DateTimeField(blank=True, null=True, verbose_name="تاريخُ الاعتماد")),
                ("rejection_reason", models.TextField(blank=True, verbose_name="سببُ الرفض")),
                ("academic_year", models.CharField(
                    default=default_academic_year,
                    max_length=9,
                    verbose_name="العام الدراسيّ",
                )),
                ("school", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="permit_requests", to="core.school")),
                ("staff", models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="permit_requests",
                    to="core.customuser",
                    verbose_name="الموظّف",
                )),
                ("reviewed_by", models.ForeignKey(
                    blank=True,
                    null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name="reviewed_permit_requests",
                    to="core.customuser",
                    verbose_name="اعتمدَهُ",
                )),
            ],
            options={
                "verbose_name": "طلبُ إذنٍ",
                "verbose_name_plural": "طلباتُ الأذونات",
                "ordering": ["-created_at"],
            },
        ),
        migrations.AddIndex(
            model_name="permitrequest",
            index=models.Index(fields=["school", "staff", "status"], name="staff_aff_perm_idx"),
        ),
        migrations.AddIndex(
            model_name="permitrequest",
            index=models.Index(fields=["school", "date", "status"], name="staff_aff_perm_date_idx"),
        ),
        migrations.AddIndex(
            model_name="permitrequest",
            index=models.Index(fields=["school", "staff", "academic_year"], name="staff_aff_perm_year_idx"),
        ),
        migrations.AddConstraint(
            model_name="permitrequest",
            constraint=models.UniqueConstraint(
                condition=models.Q(status="approved"),
                fields=["school", "staff", "date"],
                name="unique_approved_permit_per_day",
            ),
        ),
    ]

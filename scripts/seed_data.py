#!/usr/bin/env python
"""
seed_data.py — بيانات تجريبية لمدرسة الشحانية
تشغيل: python manage.py shell < scripts/seed_data.py
أو:    python manage.py seed
"""
import django, os, sys
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "shschool.settings.development")

from django.db import transaction
from django.utils import timezone
from datetime import date, time, timedelta

from core.models import School, CustomUser, Role, Membership, ClassGroup, StudentEnrollment
from operations.models import Subject, Session, StudentAttendance


def run():
    print("🌱 بدء تهيئة البيانات التجريبية...")

    with transaction.atomic():
        # ── المدرسة ───────────────────────────────────────────
        school, _ = School.objects.get_or_create(
            code="SHH",
            defaults={
                "name": "مدرسة الشحانية الإعدادية الثانوية للبنين",
                "city": "الشحانية",
            }
        )
        print(f"  ✅ المدرسة: {school}")

        # ── الأدوار ───────────────────────────────────────────
        roles = {}
        for role_name in ["principal", "vice_academic", "vice_admin", "teacher", "coordinator", "student", "specialist"]:
            r, _ = Role.objects.get_or_create(school=school, name=role_name)
            roles[role_name] = r
        print(f"  ✅ الأدوار: {len(roles)}")

        # ── المستخدمون ────────────────────────────────────────
        users_data = [
            # (national_id, full_name, password, role, is_staff)
            ("00000000001", "سلطان ناصر الهاجري",        "admin123",   "principal",     True),
            ("00000000002", "عبدالرحمن صالح الغفران",    "admin123",   "vice_admin",    False),
            ("00000000003", "جابر علي فرج",              "admin123",   "vice_academic", False),
            ("00000000004", "أحمد محمد حسن إبراهيم",    "teacher123", "teacher",       False),
            ("00000000005", "محمد نادي محمد العرامين",   "teacher123", "teacher",       False),
            ("00000000006", "حسن إبراهيم العربي الصافي", "teacher123", "teacher",       False),
            ("00000000007", "عادل محمد نصر أحمد",        "teacher123", "coordinator",   False),
            ("00000000008", "سلطان سعيد عبدالله عواد",  "teacher123", "teacher",       False),
            ("00000000009", "فيصل جليل محيميد الرويلي", "teacher123", "teacher",       False),
            ("00000000010", "خالد محمد السيد جمعه",      "teacher123", "specialist",    False),
        ]

        staff = {}
        for nid, name, pwd, role_name, is_staff in users_data:
            u, created = CustomUser.objects.get_or_create(
                national_id=nid,
                defaults={"full_name": name, "is_staff": is_staff, "is_active": True}
            )
            if created:
                u.set_password(pwd)
                u.save()
            Membership.objects.get_or_create(
                user=u, school=school, role=roles[role_name],
                defaults={"is_active": True}
            )
            staff[nid] = u

        print(f"  ✅ الموظفون: {len(staff)}")

        # ── الفصول الدراسية ───────────────────────────────────
        classes_data = [
            # (grade, section, level)
            ("G7", "1", "prep"), ("G7", "2", "prep"), ("G7", "3", "prep"),
            ("G8", "1", "prep"), ("G8", "2", "prep"),
            ("G9", "1", "prep"), ("G9", "2", "prep"),
            ("G10","1", "sec"),  ("G10","2", "sec"),
            ("G11","1", "sec"),  ("G11","2", "sec"),
            ("G12","1", "sec"),  ("G12","2", "sec"),
        ]

        class_groups = {}
        for grade, section, level in classes_data:
            cg, _ = ClassGroup.objects.get_or_create(
                school=school, grade=grade, section=section, academic_year="2025-2026",
                defaults={"level_type": level, "is_active": True}
            )
            class_groups[f"{grade}-{section}"] = cg

        print(f"  ✅ الفصول: {len(class_groups)}")

        # ── الطلاب (20 طالب تجريبي) ──────────────────────────
        student_names = [
            "يوسف سيف العليانى", "محمد أحمد الغضورى", "نواف مناحي الهاجري",
            "خالد سعد المري",    "فهد ناصر العنزي",   "عبدالله عمر القحطاني",
            "سلطان حمد الدوسري", "ماجد سلطان الشمري", "راشد خالد الكواري",
            "تميم علي المنصوري", "جاسم محمد السليطي", "أحمد ناصر الهاجري",
            "حمد سعيد المهندي",  "علي خالد العمادي",  "سعد ناصر القحطاني",
            "عمر فهد الكواري",   "نادر سعد المري",     "وليد محمد الشمري",
            "مشعل أحمد العنزي",  "بدر خالد الدوسري",
        ]

        cg_7_1 = class_groups["G7-1"]
        students = []
        for i, name in enumerate(student_names):
            nid = f"3136{34000 + i:05d}"
            u, created = CustomUser.objects.get_or_create(
                national_id=nid,
                defaults={"full_name": name, "is_active": True}
            )
            if created:
                u.set_password(nid[-6:])
                u.save()
            Membership.objects.get_or_create(
                user=u, school=school, role=roles["student"],
                defaults={"is_active": True}
            )
            StudentEnrollment.objects.get_or_create(
                student=u, class_group=cg_7_1,
                defaults={"is_active": True}
            )
            students.append(u)

        print(f"  ✅ الطلاب: {len(students)}")

        # ── المواد الدراسية ───────────────────────────────────
        subjects_data = [
            "الرياضيات", "اللغة العربية", "اللغة الإنجليزية",
            "العلوم",    "الفيزياء",      "الكيمياء",
            "الأحياء",   "التربية الإسلامية", "التربية البدنية",
            "الدراسات الاجتماعية", "تكنولوجيا المعلومات",
        ]
        subjects = {}
        for name in subjects_data:
            s, _ = Subject.objects.get_or_create(
                school=school, name_ar=name,
                defaults={"code": name[:4]}
            )
            subjects[name] = s

        print(f"  ✅ المواد: {len(subjects)}")

        # ── الحصص (3 أيام) ────────────────────────────────────
        teacher_4 = staff["00000000004"]
        teacher_5 = staff["00000000005"]
        math      = subjects["الرياضيات"]
        arabic    = subjects["اللغة العربية"]
        english   = subjects["اللغة الإنجليزية"]
        science   = subjects["العلوم"]

        today      = timezone.now().date()
        yesterday  = today - timedelta(days=1)
        day_before = today - timedelta(days=2)

        sessions_to_create = [
            # Today
            (teacher_4, cg_7_1, math,    today, time(7,30), time(8,15),  "scheduled"),
            (teacher_4, cg_7_1, arabic,  today, time(8,20), time(9,5),   "scheduled"),
            (teacher_5, cg_7_1, english, today, time(9,10), time(9,55),  "scheduled"),
            (teacher_5, cg_7_1, science, today, time(10,10),time(10,55), "scheduled"),
            # Yesterday
            (teacher_4, cg_7_1, math,    yesterday, time(7,30), time(8,15),  "completed"),
            (teacher_5, cg_7_1, english, yesterday, time(8,20), time(9,5),   "completed"),
        ]

        sessions_created = []
        for teacher, cg, subj, d, st, et, status in sessions_to_create:
            sess, created = Session.objects.get_or_create(
                school=school, teacher=teacher, class_group=cg,
                date=d, start_time=st,
                defaults={
                    "subject":    subj,
                    "end_time":   et,
                    "status":     status,
                }
            )
            sessions_created.append(sess)

        print(f"  ✅ الحصص: {len(sessions_created)}")

        # ── بيانات حضور لليوم الأمس ─────────────────────────
        completed = [s for s in sessions_created if s.status == "completed"]
        att_count = 0
        for sess in completed:
            for i, student in enumerate(students):
                status = "absent" if i in (2, 7) else "present"
                att, created = StudentAttendance.objects.get_or_create(
                    session=sess, student=student,
                    defaults={
                        "school":     school,
                        "status":     status,
                        "marked_by":  sess.teacher,
                    }
                )
                if created:
                    att_count += 1

        print(f"  ✅ سجلات الحضور: {att_count}")

        # ── جدول أسبوعي تجريبي (المرحلة 2) ──────────────────
        from operations.models import ScheduleSlot
        from datetime import time as t

        # حصص الأسبوع: (معلم, فصل, مادة, يوم, حصة, بداية, نهاية)
        weekly = [
            # أحمد — يوم الأحد
            (teacher_4, cg_7_1, math,    0, 1, t(7,30),  t(8,15)),
            (teacher_4, cg_7_1, math,    0, 2, t(8,20),  t(9,5)),
            (teacher_4, cg_8_1, math,    0, 3, t(9,10),  t(9,55)),
            # أحمد — يوم الاثنين
            (teacher_4, cg_7_1, math,    1, 1, t(7,30),  t(8,15)),
            (teacher_4, cg_8_1, math,    1, 3, t(9,10),  t(9,55)),
            # أحمد — يوم الثلاثاء
            (teacher_4, cg_7_1, math,    2, 2, t(8,20),  t(9,5)),
            # محمد — يوم الأحد
            (teacher_5, cg_7_1, english, 0, 4, t(10,10), t(10,55)),
            (teacher_5, cg_8_1, english, 0, 5, t(11,10), t(11,55)),
            # محمد — يوم الاثنين
            (teacher_5, cg_7_1, english, 1, 2, t(8,20),  t(9,5)),
            (teacher_5, cg_8_1, science, 1, 4, t(10,10), t(10,55)),
            # محمد — يوم الأربعاء
            (teacher_5, cg_7_1, english, 3, 1, t(7,30),  t(8,15)),
        ]
        slot_count = 0
        for teacher, cg, subj, day, period, start, end in weekly:
            _, created = ScheduleSlot.objects.get_or_create(
                school=school, teacher=teacher, class_group=cg,
                day_of_week=day, period_number=period, academic_year="2025-2026",
                defaults={"subject": subj, "start_time": start, "end_time": end}
            )
            if created:
                slot_count += 1
        print(f"  ✅ حصص الجدول الأسبوعي: {slot_count}")

    print("\n🎉 البيانات التجريبية جاهزة!")
    print("\n── بيانات الدخول ─────────────────────────")
    print("  مدير:  00000000001 / admin123")
    print("  معلم:  00000000004 / teacher123")
    print("  معلم:  00000000005 / teacher123")
    print("──────────────────────────────────────────")


if __name__ == "__main__":
    run()

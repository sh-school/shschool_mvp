import csv
import logging
import os

from django.core.management.base import BaseCommand
from django.db import IntegrityError

logger = logging.getLogger(__name__)
from django.db import transaction

CSV_PATH = os.path.join(os.path.dirname(__file__), "../../../scripts/new_students_full.csv")

RELATION_MAP = {
    "أب": "father",
    "ام": "mother",
    "أم": "mother",
    "والد": "father",
    "والدة": "mother",
    "وصي": "guardian",
    "وصية": "guardian",
    "أخ": "other",
    "أخت": "other",
}

GRADE_MAP = {
    "7": "الصف السابع",
    "8": "الصف الثامن",
    "9": "الصف التاسع",
    "10": "الصف العاشر",
    "11": "الصف الحادي عشر",
    "12": "الصف الثاني عشر",
}


class Command(BaseCommand):
    help = "استيراد الطلاب + أولياء الأمور + الربط من ملف CSV"

    def handle(self, *args, **options):
        from core.models import (
            ClassGroup,
            CustomUser,
            Membership,
            ParentStudentLink,
            Role,
            School,
            StudentEnrollment,
        )

        school = School.objects.first()
        if not school:
            self.stdout.write(self.style.ERROR("❌ لا توجد مدرسة. أنشئ مدرسة أولاً."))
            return

        roles = {r.name: r for r in Role.objects.all()}
        missing_roles = [r for r in ["student", "parent"] if r not in roles]
        if missing_roles:
            self.stdout.write(self.style.ERROR(f"❌ أدوار مفقودة: {missing_roles}"))
            self.stdout.write("   شغّل: python manage.py seed_data  لإنشاء الأدوار")
            return

        student_role = roles["student"]
        parent_role = roles["parent"]

        if not os.path.exists(CSV_PATH):
            self.stdout.write(self.style.ERROR(f"❌ الملف غير موجود: {CSV_PATH}"))
            self.stdout.write("   انسخ الملف إلى: scripts/new_students_full.csv")
            return

        with open(CSV_PATH, encoding="utf-8-sig") as f:
            rows = list(csv.DictReader(f))

        self.stdout.write(f"📂 تم تحميل {len(rows)} سجل\n")

        stats = {
            "students_created": 0,
            "students_updated": 0,
            "parents_created": 0,
            "parents_existed": 0,
            "links_created": 0,
            "links_existed": 0,
            "errors": [],
        }

        with transaction.atomic():
            for i, row in enumerate(rows, 1):
                student_nid = row.get("national_no", "").strip()
                student_name = row.get("studant_name", "").strip()
                student_name_en = row.get("studant_englisf_name", "").strip()
                dob = row.get("date_of_birth", "").strip()
                grade = row.get("grade", "").strip()
                section = row.get("section", "").strip()
                parent_nid = row.get("parent_national_no", "").strip()
                parent_name = row.get("name_parent", "").strip()
                relation_ar = row.get("relation_parent", "").strip()
                parent_phones = row.get("parent_phone_no", "").strip()
                parent_phone = parent_phones.split(",")[0].strip() if parent_phones else ""
                parent_email = row.get("parent_email", "").strip()
                if parent_email == "-":
                    parent_email = ""

                if not student_nid:
                    stats["errors"].append(f"سطر {i}: رقم وطني فارغ")
                    continue

                student, s_created = CustomUser.objects.get_or_create(
                    national_id=student_nid,
                    defaults={
                        "full_name": student_name,
                        "is_active": True,
                    },
                )

                if s_created:
                    student.set_password(student_nid)
                    student.save()
                    stats["students_created"] += 1
                else:
                    changed = False
                    if not student.full_name and student_name:
                        student.full_name = student_name
                        changed = True
                    if changed:
                        student.save()
                        stats["students_updated"] += 1

                Membership.objects.get_or_create(
                    user=student, school=school, role=student_role, defaults={"is_active": True}
                )

                if grade and section:
                    try:
                        class_group = ClassGroup.objects.filter(
                            school=school, grade__icontains=grade, section=section, is_active=True
                        ).first()
                        if class_group:
                            StudentEnrollment.objects.get_or_create(
                                student=student,
                                class_group=class_group,
                                defaults={"is_active": True},
                            )
                    except (IntegrityError, ValueError) as e:
                        logger.warning("فشل ربط الطالب بالفصل الدراسي: %s", e)

                if not parent_nid:
                    stats["errors"].append(f"سطر {i}: رقم ولي الأمر فارغ — الطالب {student_nid}")
                    continue

                parent, p_created = CustomUser.objects.get_or_create(
                    national_id=parent_nid,
                    defaults={
                        "full_name": parent_name,
                        "email": parent_email,
                        "phone": parent_phone,
                        "is_active": True,
                    },
                )

                if p_created:
                    parent.set_password(parent_nid)
                    parent.save()
                    stats["parents_created"] += 1
                else:
                    stats["parents_existed"] += 1
                    changed = False
                    if not parent.full_name and parent_name:
                        parent.full_name = parent_name
                        changed = True
                    if not parent.phone and parent_phone:
                        parent.phone = parent_phone
                        changed = True
                    if not parent.email and parent_email:
                        parent.email = parent_email
                        changed = True
                    if changed:
                        parent.save()

                Membership.objects.get_or_create(
                    user=parent, school=school, role=parent_role, defaults={"is_active": True}
                )

                rel = RELATION_MAP.get(relation_ar, "father")
                link, l_created = ParentStudentLink.objects.get_or_create(
                    parent=parent,
                    student=student,
                    school=school,
                    defaults={
                        "relationship": rel,
                        "is_primary": True,
                        "can_view_grades": True,
                        "can_view_attendance": True,
                    },
                )

                if l_created:
                    stats["links_created"] += 1
                else:
                    stats["links_existed"] += 1

                if i % 100 == 0:
                    self.stdout.write(f"  ⏳ معالجة {i}/{len(rows)} سجل...")

        self.stdout.write("\n" + "━" * 55)
        self.stdout.write("📊  نتيجة الاستيراد الشاملة")
        self.stdout.write("━" * 55)
        self.stdout.write(f"👨‍🎓 طلاب جدد أُنشئوا:          {stats['students_created']:>4}")
        self.stdout.write(f"👨‍🎓 طلاب موجودون (تم تحديثهم): {stats['students_updated']:>4}")
        self.stdout.write(f"👨‍👩‍👧 أولياء أمر جدد:            {stats['parents_created']:>4}")
        self.stdout.write(f"👨‍👩‍👧 أولياء أمر موجودون:         {stats['parents_existed']:>4}")
        self.stdout.write(f"🔗 روابط جديدة أُنشئت:         {stats['links_created']:>4}")
        self.stdout.write(f"🔗 روابط كانت موجودة:          {stats['links_existed']:>4}")
        self.stdout.write(f"⚠️  أخطاء:                      {len(stats['errors']):>4}")

        if stats["errors"]:
            self.stdout.write("\nأول 15 خطأ:")
            for e in stats["errors"][:15]:
                self.stdout.write(f"  • {e}")
            if len(stats["errors"]) > 15:
                self.stdout.write(f"  ... و {len(stats['errors']) - 15} خطأ آخر")

        self.stdout.write("━" * 55)
        self.stdout.write("✅ اكتمل الاستيراد بنجاح\n")
        self.stdout.write("ملاحظة: كلمة المرور الافتراضية = الرقم الوطني للمستخدم")
        self.stdout.write("        يُنصح بإخبار أولياء الأمور بتغييرها أول دخول\n")

"""
سكريبت ربط أولياء الأمور بالطلاب من ملف new_students_full.csv
الاستخدام: python manage.py shell < scripts/link_parents_students.py
        أو: python manage.py runscript link_parents_students  (مع django-extensions)
"""
import csv, sys, os
from django.db import transaction

CSV_PATH = os.path.join(os.path.dirname(__file__), "new_students_full.csv")

# خريطة صلة القرابة عربي → choices
RELATION_MAP = {
    "أب":    "father",
    "ام":    "mother",
    "أم":    "mother",
    "والد":  "father",
    "والدة": "mother",
    "وصي":   "guardian",
    "وصية":  "guardian",
}

def run():
    from core.models import CustomUser, School, Membership, Role, ParentStudentLink

    school = School.objects.first()
    if not school:
        print("❌ لا توجد مدرسة في قاعدة البيانات")
        return

    try:
        parent_role = Role.objects.get(name="parent")
        student_role = Role.objects.get(name="student")
    except Role.DoesNotExist as e:
        print(f"❌ دور غير موجود: {e}")
        return

    stats = {
        "students_found":  0,
        "students_missing": 0,
        "parents_created": 0,
        "parents_found":   0,
        "links_created":   0,
        "links_existed":   0,
        "errors":          [],
    }

    with open(CSV_PATH, encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))

    print(f"📂 تحميل {len(rows)} سجل من الملف...")

    with transaction.atomic():
        for i, row in enumerate(rows, 1):
            student_id   = row.get("national_no", "").strip()
            parent_id    = row.get("parent_national_no", "").strip()
            parent_name  = row.get("name_parent", "").strip()
            relation_ar  = row.get("relation_parent", "").strip()
            parent_phone = row.get("parent_phone_no", "").strip().split(",")[0].strip()
            parent_email = row.get("parent_email", "").strip()

            if not student_id or not parent_id:
                stats["errors"].append(f"سطر {i}: رقم وطني ناقص")
                continue

            # 1. ابحث عن الطالب
            try:
                student = CustomUser.objects.get(national_id=student_id)
                stats["students_found"] += 1
            except CustomUser.DoesNotExist:
                stats["students_missing"] += 1
                stats["errors"].append(f"❌ طالب غير موجود: {student_id} — {row.get('studant_name','')}")
                continue

            # 2. ابحث عن ولي الأمر أو أنشئه
            parent, created = CustomUser.objects.get_or_create(
                national_id=parent_id,
                defaults={
                    "full_name": parent_name,
                    "email":     parent_email if parent_email != "-" else "",
                    "phone":     parent_phone,
                    "is_active": True,
                }
            )

            if created:
                parent.set_unusable_password()
                parent.save()
                stats["parents_created"] += 1
            else:
                stats["parents_found"] += 1
                # تحديث البيانات لو ناقصة
                updated = False
                if not parent.full_name and parent_name:
                    parent.full_name = parent_name
                    updated = True
                if not parent.phone and parent_phone:
                    parent.phone = parent_phone
                    updated = True
                if not parent.email and parent_email and parent_email != "-":
                    parent.email = parent_email
                    updated = True
                if updated:
                    parent.save()

            # 3. تأكد أن ولي الأمر عضو في المدرسة
            Membership.objects.get_or_create(
                user=parent, school=school, role=parent_role,
                defaults={"is_active": True}
            )

            # 4. أنشئ الرابط
            rel = RELATION_MAP.get(relation_ar, "father")
            link, link_created = ParentStudentLink.objects.get_or_create(
                parent=parent, student=student, school=school,
                defaults={
                    "relationship": rel,
                    "is_primary":   True,
                    "can_view_grades":     True,
                    "can_view_attendance": True,
                }
            )

            if link_created:
                stats["links_created"] += 1
            else:
                stats["links_existed"] += 1

            if i % 50 == 0:
                print(f"  ✓ معالجة {i}/{len(rows)}...")

    # التقرير النهائي
    print("\n" + "="*50)
    print("📊 نتيجة الاستيراد:")
    print(f"  ✅ طلاب تم إيجادهم:       {stats['students_found']}")
    print(f"  ❌ طلاب غير موجودين:      {stats['students_missing']}")
    print(f"  👤 أولياء أمر جدد:         {stats['parents_created']}")
    print(f"  👤 أولياء أمر موجودون:     {stats['parents_found']}")
    print(f"  🔗 روابط جديدة أُنشئت:    {stats['links_created']}")
    print(f"  🔗 روابط كانت موجودة:     {stats['links_existed']}")
    if stats["errors"][:10]:
        print(f"\n⚠️  أول {min(10,len(stats['errors']))} أخطاء:")
        for e in stats["errors"][:10]:
            print(f"    {e}")
    if len(stats["errors"]) > 10:
        print(f"    ... و {len(stats['errors'])-10} خطأ آخر")
    print("="*50)

run()

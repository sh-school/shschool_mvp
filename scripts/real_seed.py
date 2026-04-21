#!/usr/bin/env python
"""
real_seed.py — حقن البيانات الحقيقية لمدرسة الشحانية
يشمل: الموظفين، الطلاب، أولياء الأمور، الفصول، الخطة التشغيلية، لجنة الجودة

تشغيل:
    python manage.py shell < scripts/real_seed.py
أو:
    python manage.py real_seed
"""

import csv
import os
import re
import secrets
from pathlib import Path

_SEED_PASSWORD = os.environ.get("SEED_DEFAULT_PASSWORD", secrets.token_urlsafe(12))

BASE_DIR = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "data"

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "shschool.settings.development")

import django

django.setup()

from django.db import transaction

from core.models import ClassGroup, CustomUser, Membership, Profile, Role, School, StudentEnrollment


# ─────────────────────────────────────────────────────────────
# خريطة المسميات الوظيفية → أدوار النظام
# ─────────────────────────────────────────────────────────────
def map_role(job_title_norm: str) -> str:
    t = job_title_norm.strip().lower()
    if "مدير المدرسه" in t:
        return "principal"
    if "النائب الاداري" in t:
        return "vice_admin"
    if "نائب المدير للشؤون" in t:
        return "vice_academic"
    if t.startswith("منسق"):
        return "coordinator"
    if t.startswith("معلم"):
        return "teacher"
    if "اخصائي" in t or "مرشد" in t:
        return "specialist"
    return "admin"


def clean(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def read_csv(filename: str):
    path = SCRIPTS_DIR / filename
    with open(path, encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


# ─────────────────────────────────────────────────────────────
# الدالة الرئيسية
# ─────────────────────────────────────────────────────────────
def run():
    print("🏫 حقن البيانات الحقيقية — مدرسة الشحانية\n")

    with transaction.atomic():
        # ═══════════════════════════════════════════════════
        # 1. المدرسة
        # ═══════════════════════════════════════════════════
        school, _ = School.objects.get_or_create(
            code="SHH",
            defaults={
                "name": "مدرسة الشحانية الإعدادية الثانوية للبنين",
                "city": "الشحانية",
            },
        )
        print(f"✅ المدرسة: {school.name}")

        # ═══════════════════════════════════════════════════
        # 2. إنشاء الأدوار
        # ═══════════════════════════════════════════════════
        all_role_names = [
            "principal",
            "vice_admin",
            "vice_academic",
            "coordinator",
            "teacher",
            "specialist",
            "admin",
            "student",
            "parent",
        ]
        role_objs = {}
        for rname in all_role_names:
            role, _ = Role.objects.get_or_create(school=school, name=rname)
            role_objs[rname] = role
        print(f"✅ الأدوار: {len(role_objs)} دور")

        # ═══════════════════════════════════════════════════
        # 3. الموظفون
        # ═══════════════════════════════════════════════════
        staff_rows = read_csv("2_Normalized_Staff_List.csv")
        staff_created = 0
        staff_map = {}  # national_no → user

        for row in staff_rows:
            nat_id = clean(row.get("national_no", ""))
            name = clean(row.get("stuff _name", ""))
            job_norm = clean(row.get("job_title_norm", ""))
            job_orig = clean(row.get("job_title", ""))
            email = clean(row.get("email", ""))
            phone = clean(row.get("phone_no", ""))
            job_no = clean(row.get("job_no", ""))

            if not nat_id or not name:
                continue

            user, created = CustomUser.objects.get_or_create(
                national_id=nat_id,
                defaults={
                    "full_name": name,
                    "email": email,
                    "phone": phone,
                    "is_staff": True,
                },
            )
            if not created:
                # تحديث المعلومات
                user.full_name = name
                user.email = email or user.email
                user.phone = phone or user.phone
                user.is_staff = True
                user.save(update_fields=["full_name", "email", "phone", "is_staff"])

            # كلمة المرور الافتراضية
            if not user.password or user.password == "":
                user.set_password(_SEED_PASSWORD)
                user.save(update_fields=["password"])

            # ملف شخصي
            Profile.objects.get_or_create(user=user)

            # هل المدير؟
            if "مدير المدرسه" in job_norm:
                user.is_superuser = True
                user.save(update_fields=["is_superuser"])

            # العضوية
            role_name = map_role(job_norm)
            role_obj = role_objs[role_name]
            Membership.objects.get_or_create(
                user=user, school=school, role=role_obj, defaults={"is_active": True}
            )

            staff_map[nat_id] = user
            if created:
                staff_created += 1

        print(f"✅ الموظفون: {len(staff_rows)} مُعالَج ({staff_created} جديد)")
        print(f"   — مدير: {school.memberships.filter(role__name='principal').count()}")
        print(f"   — معلمون: {school.memberships.filter(role__name='teacher').count()}")
        print(f"   — منسقون: {school.memberships.filter(role__name='coordinator').count()}")
        print(f"   — أخصائيون: {school.memberships.filter(role__name='specialist').count()}")
        print(f"   — إداريون: {school.memberships.filter(role__name='admin').count()}")

        # ═══════════════════════════════════════════════════
        # 4. الفصول الدراسية من بيانات الطلاب
        # ═══════════════════════════════════════════════════
        student_rows = read_csv("new_students_full.csv")

        GRADE_MAP = {
            "7": "G7",
            "8": "G8",
            "9": "G9",
            "10": "G10",
            "11": "G11",
            "12": "G12",
        }
        LEVEL_MAP = {
            "7": "prep",
            "8": "prep",
            "9": "prep",
            "10": "sec",
            "11": "sec",
            "12": "sec",
        }

        # جمع الشعب الفريدة
        unique_sections = {}
        for row in student_rows:
            grade = str(row.get("grade", "")).strip()
            section = str(row.get("section", "")).strip()
            if not grade or not section:
                continue
            key = (grade, section)
            unique_sections[key] = True

        class_map = {}  # (grade, section) → ClassGroup
        cg_created = 0
        for grade, section in sorted(unique_sections.keys()):
            grade_code = GRADE_MAP.get(grade)
            if not grade_code:
                continue
            cg, created = ClassGroup.objects.get_or_create(
                school=school,
                grade=grade_code,
                section=section,
                academic_year="2025-2026",
                defaults={
                    "level_type": LEVEL_MAP.get(grade, "prep"),
                    "is_active": True,
                },
            )
            class_map[(grade, section)] = cg
            if created:
                cg_created += 1

        print(f"\n✅ الفصول الدراسية: {len(class_map)} فصل ({cg_created} جديد)")

        # ═══════════════════════════════════════════════════
        # 5. الطلاب + أولياء الأمور + التسجيل
        # ═══════════════════════════════════════════════════
        parent_role = role_objs["parent"]
        student_role = role_objs["student"]

        stu_created = 0
        par_created = 0
        enr_created = 0
        skip_count = 0

        for row in student_rows:
            nat_id = clean(row.get("national_no", ""))
            name_ar = clean(row.get("studant_name", ""))
            name_en = clean(row.get("studant_englisf_name", ""))
            dob = clean(row.get("date_of_birth", ""))
            needs = clean(row.get("needs", ""))
            grade = str(row.get("grade", "")).strip()
            section = str(row.get("section", "")).strip()
            par_nat = clean(row.get("parent_national_no", ""))
            par_name = clean(row.get("name_parent", ""))
            par_rel = clean(row.get("relation_parent", ""))
            par_phone = clean(row.get("parent_phone_no", "")).split(",")[0].strip()
            par_email = clean(row.get("parent_email", ""))

            if not nat_id or not name_ar:
                skip_count += 1
                continue

            # ── الطالب ──
            student, s_created = CustomUser.objects.get_or_create(
                national_id=nat_id,
                defaults={
                    "full_name": name_ar,
                    "is_staff": False,
                    "is_active": True,
                },
            )
            if not s_created:
                student.full_name = name_ar
                student.save(update_fields=["full_name"])

            if not student.password or student.password == "":
                student.set_password(_SEED_PASSWORD)
                student.save(update_fields=["password"])

            # ملف شخصي مع الملاحظات
            profile_notes = ""
            if needs and needs not in ("لا", "-", ""):
                profile_notes = f"احتياجات خاصة: {needs}"
            Profile.objects.get_or_create(user=student, defaults={"notes": profile_notes})

            # عضوية الطالب
            Membership.objects.get_or_create(
                user=student, school=school, role=student_role, defaults={"is_active": True}
            )

            # تسجيل في الفصل
            cg = class_map.get((grade, section))
            if cg:
                enr, e_created = StudentEnrollment.objects.get_or_create(
                    student=student, class_group=cg, defaults={"is_active": True}
                )
                if e_created:
                    enr_created += 1

            if s_created:
                stu_created += 1

            # ── ولي الأمر ──
            if par_nat and par_name:
                parent, p_created = CustomUser.objects.get_or_create(
                    national_id=par_nat,
                    defaults={
                        "full_name": par_name,
                        "phone": par_phone,
                        "email": par_email if par_email not in ("-", "") else "",
                        "is_staff": False,
                        "is_active": True,
                    },
                )
                if not p_created:
                    parent.full_name = par_name
                    parent.save(update_fields=["full_name"])

                if not parent.password or parent.password == "":
                    parent.set_password(_SEED_PASSWORD)
                    parent.save(update_fields=["password"])

                Profile.objects.get_or_create(
                    user=parent, defaults={"notes": f"علاقة: {par_rel} | ابنه: {name_ar}"}
                )

                Membership.objects.get_or_create(
                    user=parent, school=school, role=parent_role, defaults={"is_active": True}
                )

                if p_created:
                    par_created += 1

        print(f"\n✅ الطلاب: {len(student_rows) - skip_count} مُعالَج ({stu_created} جديد)")
        print(f"✅ أولياء الأمور: {par_created} جديد")
        print(f"✅ التسجيلات في الفصول: {enr_created} تسجيل")
        if skip_count:
            print(f"⚠️  تجاهل: {skip_count} سجل ناقص")

        # ═══════════════════════════════════════════════════
        # 6. ربط المنسقين بالخطة التشغيلية — ملخص
        # ═══════════════════════════════════════════════════
        plan_rows = read_csv("1_Clean_Operational_Plan.csv")
        quality_rows = read_csv("4_Quality_Structure_v2.csv")
        exec_rows = read_csv("3_Unique_Executors_Inventory.csv")

        # إحصائيات الخطة
        domains = {}
        statuses = {}
        for r in plan_rows:
            d = r.get("rank_name", "").strip()
            s = r.get("status", "").strip()
            domains[d] = domains.get(d, 0) + 1
            statuses[s] = statuses.get(s, 0) + 1

        print(f"\n📋 الخطة التشغيلية: {len(plan_rows)} إجراء")
        for d, c in sorted(domains.items(), key=lambda x: -x[1]):
            print(f"   {c:4d}  {d}")
        print(f"   الحالات: {statuses}")

        # لجنة الجودة
        print(f"\n🏛️  لجنة المراجعة الذاتية: {len(quality_rows)-1} عضو")
        for r in quality_rows:
            title = r.get("المسمى الوظيفي", "").strip()
            resp = r.get("المسؤولية", "").strip()
            field = r.get("المجال المسؤول عنه", "").strip()
            if title:
                # ابحث عن الموظف المطابق
                matched = school.memberships.filter(
                    user__full_name__icontains=title.replace("منسق ", "")
                ).first()
                mark = "✓" if matched else "·"
                print(f"   {mark} {title:<35} {resp:<20} {field}")

        # ═══════════════════════════════════════════════════
        # 7. إنشاء superuser إذا لم يوجد
        # ═══════════════════════════════════════════════════
        principal_user = (
            school.memberships.filter(role__name="principal").select_related("user").first()
        )
        if principal_user:
            u = principal_user.user
            u.is_superuser = True
            u.is_staff = True
            u.save(update_fields=["is_superuser", "is_staff"])
            print(f"\n🔑 المدير (superuser): {u.full_name} | رقم: {u.national_id}")

    # ═══════════════════════════════════════════════════
    # ملخص نهائي
    # ═══════════════════════════════════════════════════
    print("\n" + "═" * 55)
    print("🎉 اكتملت عملية الحقن!")
    print("═" * 55)
    print(f"  مجموع المستخدمين:    {CustomUser.objects.count()}")
    print(
        f"  موظفون:              {school.memberships.filter(role__name__in=['principal','vice_admin','vice_academic','coordinator','teacher','specialist','admin']).count()}"
    )
    print(f"  طلاب:                {school.memberships.filter(role__name='student').count()}")
    print(f"  أولياء أمور:         {school.memberships.filter(role__name='parent').count()}")
    print(f"  فصول دراسية:         {ClassGroup.objects.filter(school=school).count()}")
    print(
        f"  تسجيلات الطلاب:      {StudentEnrollment.objects.filter(class_group__school=school).count()}"
    )
    print("\n── بيانات الدخول ─────────────────────────────────────")
    print(f"  كلمة المرور الموحدة: {_SEED_PASSWORD}")
    if principal_user:
        print(f"  المدير:    {principal_user.user.national_id}")
    print("  المعلمون:  <الرقم الشخصي>")
    print("  الطلاب:    <الرقم الشخصي>")
    print("  الأولياء:  <الرقم الشخصي>")
    print("═" * 55)


if __name__ == "__main__":
    run()

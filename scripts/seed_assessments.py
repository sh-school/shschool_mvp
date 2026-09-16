#!/usr/bin/env python
"""
seed_assessments.py — بيانات تجريبية للتقييمات
يطبّق بنيةَ الباقات من `GradeService.ensure_packages` (القرار 14/2018، المادّة 3).
"""

import csv
import os
import random
from decimal import Decimal
from pathlib import Path

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "shschool.settings.development")
import django

django.setup()

from django.db import transaction

from assessments.models import (
    Assessment,
    AssessmentPackage,
    StudentAssessmentGrade,
    SubjectClassSetup,
)
from assessments.services import GradeService, PackageStructureError
from core.academic_calendar import academic_year_for_school
from core.models import ClassGroup, CustomUser, School, StudentEnrollment
from operations.models import Subject

# المواد الإعدادية (G7–G9)
PREP_SUBJECTS = [
    ("الرياضيات", "MATH"),
    ("اللغة العربية", "ARB"),
    ("اللغة الإنجليزية", "ENG"),
    ("العلوم", "SCI"),
    ("التربية الإسلامية", "ISL"),
    ("الدراسات الاجتماعية", "SOC"),
    ("التربية البدنية", "PE"),
    ("تكنولوجيا المعلومات", "ICT"),
]
# المواد الثانوية (G10–G12)
SEC_SUBJECTS = [
    ("الرياضيات", "MATH"),
    ("اللغة العربية", "ARB"),
    ("اللغة الإنجليزية", "ENG"),
    ("التربية الإسلامية", "ISL"),
    ("الفيزياء", "PHY"),
    ("الكيمياء", "CHEM"),
    ("الأحياء", "BIO"),
    ("تكنولوجيا المعلومات", "ICT"),
]

SUBJECT_COORDINATOR = {
    "الرياضيات": "منسق الرياضيات",
    "اللغة العربية": "منسق اللغه العربيه",
    "اللغة الإنجليزية": "منسق اللغه الانجليزيه",
    "العلوم": "منسق العلوم",
    "التربية الإسلامية": "منسق التربيه الاسلاميه",
    "الدراسات الاجتماعية": "منسق الدراسات الاجتماعيه",
    "التربية البدنية": "منسق التربيه البدنيه",
    "الفيزياء": "منسق الفيزياء",
    "الكيمياء": "منسق كيمياء",
    "الأحياء": "منسق الاحياء",
    "تكنولوجيا المعلومات": "منسق تكنولوجيا المعلومات",
    "الفنون البصرية": "منسق الفنون البصريه",
}

# ── الباقاتُ من `GradeService.ensure_packages` — جدولُ `core.domain.grades.package_weights`
# (القرار 14/2018، المادّة 3): 4–11 منتصفٌ ونهايةٌ وأعمالٌ في كلّ فصل، والثاني عشر
# P2 (40) وP4 (60) لا غير. كان هنا جدولٌ ثانٍ يُنشئ P1/P3 لكلّ الصفوف.

# تقييمات داخل كل باقة نشطة
ASSESSMENTS_IN_PACKAGE = {
    ("S1", "P1"): [
        {"title": "اختبار منتصف الفصل الأول", "type": "exam", "weight": 100, "max": Decimal("15")}
    ],
    ("S1", "P2"): [
        {"title": "اختبار نهاية الفصل الأول", "type": "exam", "weight": 100, "max": Decimal("20")}
    ],
    ("S1", "AW"): [
        {"title": "أعمال صفية", "type": "classwork", "weight": 50, "max": Decimal("10")},
        {"title": "واجبات منزلية", "type": "homework", "weight": 50, "max": Decimal("10")},
    ],
    ("S2", "P3"): [
        {"title": "اختبار منتصف الفصل الثاني", "type": "exam", "weight": 100, "max": Decimal("15")}
    ],
    ("S2", "P4"): [
        {"title": "اختبار نهاية العام", "type": "exam", "weight": 100, "max": Decimal("40")}
    ],
    ("S2", "AW"): [
        {"title": "أعمال صفية", "type": "classwork", "weight": 50, "max": Decimal("10")},
        {"title": "واجبات منزلية", "type": "homework", "weight": 50, "max": Decimal("10")},
    ],
}


def run():
    print("📝 حقن بيانات التقييمات بالأوزان القطرية الصحيحة...\n")
    school = School.objects.get(code="SHH")
    year = "2025-2026"

    # خريطة job_title → user
    DATA_DIR = Path(__file__).resolve().parent.parent / "data"
    with open(DATA_DIR / "2_Normalized_Staff_List.csv", encoding="utf-8-sig") as f:
        staff_rows = list(csv.DictReader(f))
    nat_to_job = {r["national_no"].strip(): r.get("job_title_norm", "").strip() for r in staff_rows}
    job_to_user = {}
    for u in CustomUser.objects.filter(memberships__school=school, is_staff=True).distinct():
        jt = nat_to_job.get(u.national_id, "")
        if jt and jt not in job_to_user:
            job_to_user[jt] = u

    principal = school.memberships.filter(role__name="principal").first()
    default_user = (
        principal.user if principal else CustomUser.objects.filter(is_superuser=True).first()
    )

    with transaction.atomic():
        # ── 1. المواد ─────────────────────────────────────────
        subj_map = {}
        all_subjs = set(PREP_SUBJECTS) | set(SEC_SUBJECTS)
        for name, code in all_subjs:
            s, _ = Subject.objects.get_or_create(
                school=school, name_ar=name, defaults={"code": code}
            )
            subj_map[name] = s
        print(f"  ✅ المواد: {len(subj_map)}")

        # ── 2. إعدادات المواد + الباقات ───────────────────────
        classes = ClassGroup.objects.filter(
            school=school, academic_year=year, is_active=True
        ).in_school_order()

        setups_n = packages_n = 0
        for cg in classes:
            subj_list = PREP_SUBJECTS if cg.level_type == "prep" else SEC_SUBJECTS
            for name, _ in subj_list:
                subj = subj_map.get(name)
                if not subj:
                    continue
                coord = SUBJECT_COORDINATOR.get(name, "")
                teacher = job_to_user.get(coord, default_user)

                setup, sc = SubjectClassSetup.objects.get_or_create(
                    school=school,
                    subject=subj,
                    class_group=cg,
                    academic_year=year,
                    defaults={"teacher": teacher, "is_active": True},
                )
                if sc:
                    setups_n += 1

                # الباقات بحسب الصفّ — الثاني عشر P2/P4 فقط
                for sem in ("S1", "S2"):
                    before = AssessmentPackage.objects.filter(setup=setup, semester=sem).count()
                    try:
                        after = len(GradeService.align_packages(setup, sem))
                    except PackageStructureError as exc:
                        print(f"  ⚠️  {exc}")
                        continue
                    packages_n += after - before

        print(f"  ✅ إعدادات: {setups_n} | باقات: {packages_n}")

        # ── 3. تقييمات داخل الباقات ───────────────────────────
        asmnt_n = 0
        for (sem, ptype), asmnt_list in ASSESSMENTS_IN_PACKAGE.items():
            packages = AssessmentPackage.objects.filter(
                school=school, package_type=ptype, semester=sem, weight__gt=0
            )
            for pkg in packages:
                for ad in asmnt_list:
                    _, an = Assessment.objects.get_or_create(
                        package=pkg,
                        title=ad["title"],
                        defaults={
                            "school": school,
                            "assessment_type": ad["type"],
                            "max_grade": ad["max"],
                            "weight_in_package": Decimal(str(ad["weight"])),
                            "status": "published",
                            "created_by": pkg.setup.teacher,
                        },
                    )
                    if an:
                        asmnt_n += 1
        print(f"  ✅ التقييمات: {asmnt_n}")

        # ── 4. درجات تجريبية لـ G7 فقط ───────────────────────
        sample = ClassGroup.objects.filter(school=school, academic_year=year, grade="G7")[:2]

        grades_n = results_n = 0
        for cg in sample:
            students = StudentEnrollment.objects.filter(
                class_group=cg, is_active=True
            ).select_related("student")[:30]

            setups_c = SubjectClassSetup.objects.filter(
                school=school, class_group=cg, academic_year=year
            )
            for setup in setups_c:
                for sem in ("S1", "S2"):
                    pkgs = AssessmentPackage.objects.filter(setup=setup, semester=sem, weight__gt=0)
                    for pkg in pkgs:
                        for asmnt in pkg.assessments.filter(status="published"):
                            for enr in students:
                                is_absent = random.random() < 0.04
                                grade = None
                                if not is_absent:
                                    mx = float(asmnt.max_grade)
                                    r = random.random()
                                    if r < 0.12:
                                        g = random.uniform(0, mx * 0.49)
                                    elif r < 0.35:
                                        g = random.uniform(mx * 0.5, mx * 0.69)
                                    else:
                                        g = random.uniform(mx * 0.7, mx)
                                    grade = round(Decimal(str(g)), 1)

                                StudentAssessmentGrade.objects.update_or_create(
                                    assessment=asmnt,
                                    student=enr.student,
                                    defaults={
                                        "school": school,
                                        "grade": grade,
                                        "is_absent": is_absent,
                                        "entered_by": setup.teacher,
                                    },
                                )
                                grades_n += 1
                            asmnt.status = "graded"
                            asmnt.save(update_fields=["status"])

                # الحكمُ على الطلبة في موادّ الشعبة كلِّها — مرّةً بعد رصد الفصلين، وللعام
                # الجاري وحدَه (الأعوامُ المغلقة مجمَّدة).
                if year == academic_year_for_school(school):
                    results_n += GradeService.recalculate_students(
                        cg, year, [enr.student for enr in students], setup
                    )

        print(f"  ✅ الدرجات: {grades_n} | النتائج السنوية: {results_n}")

    from assessments.models import AnnualSubjectResult
    from core.domain.grades import FAILING_STATUSES, PASSING_STATUSES

    passed = AnnualSubjectResult.objects.filter(school=school, status__in=PASSING_STATUSES).count()
    failed = AnnualSubjectResult.objects.filter(school=school, status__in=FAILING_STATUSES).count()
    incomp = AnnualSubjectResult.objects.filter(school=school, status="incomplete").count()

    print("\n" + "═" * 55)
    print("🎉 اكتمل حقن التقييمات!")
    print(f"  ناجح: {passed}  |  راسب: {failed}  |  غير مكتمل: {incomp}")
    print("\n📐 البنية: 4–11 منتصف/نهاية/أعمال · الثاني عشر P2=40 وP4=60")
    print("  درجة النجاح السنوية: 50 من 100")
    print("═" * 55)


if __name__ == "__main__":
    run()

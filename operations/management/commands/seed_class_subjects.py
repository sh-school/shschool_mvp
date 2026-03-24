"""
seed_class_subjects.py — توزيع المواد على الفصول حسب أنصبة وزارة التربية قطر 2025-2026
المعلم = فارغ (يُدخل يدوياً من لوحة الإدارة)

مدرسة الشحانية الإعدادية الثانوية للبنين:
- G7-G9: إعدادي (34 حصة/أسبوع)
- G10: ثانوي عام (35 حصة/أسبوع)
- G11-1: علمي | G11-2,3: آداب | G11-4: تكنولوجي
- G12-1: علمي | G12-2,3,4: آداب
"""

from django.core.management.base import BaseCommand
from django.conf import settings

from core.models import ClassGroup, School
from operations.models import Subject, SubjectClassAssignment


# ── أنصبة المواد حسب المرحلة والمسار ──

PREP_SUBJECTS = {
    # المرحلة الإعدادية G7-G9 (34 حصة/أسبوع)
    "اللغة العربية": 5,
    "اللغة الإنجليزية": 5,
    "الرياضيات": 5,
    "العلوم": 4,
    "التربية الإسلامية": 4,
    "الدراسات الاجتماعية": 3,
    "الحوسبة وتكنولوجيا المعلومات": 2,
    "التربية البدنية": 2,
    "الفنون البصرية": 2,
    "المهارات الحياتية والمهنية": 2,
}  # المجموع = 34

G10_SUBJECTS = {
    # الصف العاشر (35 حصة/أسبوع)
    "اللغة العربية": 5,
    "اللغة الإنجليزية": 5,
    "الرياضيات": 5,
    "الكيمياء": 3,
    "الأحياء": 3,
    "التربية الإسلامية": 3,
    "الدراسات الاجتماعية": 3,
    "الفيزياء": 2,
    "الحوسبة وتكنولوجيا المعلومات": 2,
    "التربية البدنية": 2,
    "المهارات الحياتية والمهنية": 2,
}  # المجموع = 35

SCIENCE_11_SUBJECTS = {
    # الصف 11 علمي (35 حصة/أسبوع)
    "اللغة العربية": 5,
    "اللغة الإنجليزية": 5,
    "الرياضيات": 5,
    "الكيمياء": 4,
    "الفيزياء": 4,
    "الأحياء": 3,
    "التربية الإسلامية": 3,
    "التربية البدنية": 2,
    "المهارات الحياتية والمهنية": 2,
    "الحوسبة وتكنولوجيا المعلومات": 2,
}  # المجموع = 35

ARTS_11_SUBJECTS = {
    # الصف 11 آداب (35 حصة/أسبوع)
    "اللغة العربية": 6,
    "اللغة الإنجليزية": 5,
    "الجغرافيا": 4,
    "التاريخ": 4,
    "العلوم العامة": 4,
    "الرياضيات العامة": 3,
    "التربية الإسلامية": 3,
    "التربية البدنية": 2,
    "المهارات الحياتية والمهنية": 2,
    "الحوسبة وتكنولوجيا المعلومات": 2,
}  # المجموع = 35

TECH_11_SUBJECTS = {
    # الصف 11 تكنولوجي (35 حصة/أسبوع)
    "اللغة العربية": 5,
    "اللغة الإنجليزية": 5,
    "الرياضيات": 5,
    "الفيزياء": 4,
    "الحوسبة وتكنولوجيا المعلومات": 4,
    "الكيمياء": 3,
    "التربية الإسلامية": 3,
    "التربية البدنية": 2,
    "المهارات الحياتية والمهنية": 2,
    "الأحياء": 2,
}  # المجموع = 35

SCIENCE_12_SUBJECTS = {
    # الصف 12 علمي (35 حصة/أسبوع)
    "اللغة العربية": 5,
    "اللغة الإنجليزية": 6,
    "الرياضيات": 5,
    "الكيمياء": 4,
    "الفيزياء": 4,
    "الأحياء": 3,
    "التربية الإسلامية": 3,
    "التربية البدنية": 1,
    "المهارات الحياتية والمهنية": 2,
    "الحوسبة وتكنولوجيا المعلومات": 2,
}  # المجموع = 35

ARTS_12_SUBJECTS = {
    # الصف 12 آداب (35 حصة/أسبوع)
    "اللغة العربية": 6,
    "اللغة الإنجليزية": 6,
    "الجغرافيا": 4,
    "التاريخ": 4,
    "العلوم العامة": 4,
    "الرياضيات العامة": 3,
    "التربية الإسلامية": 3,
    "التربية البدنية": 1,
    "المهارات الحياتية والمهنية": 2,
    "الحوسبة وتكنولوجيا المعلومات": 2,
}  # المجموع = 35

# مواد تحتاج معمل
LAB_SUBJECTS = {"العلوم", "الكيمياء", "الفيزياء", "الأحياء", "الحوسبة وتكنولوجيا المعلومات"}


def get_subject_plan(grade, section):
    """تحديد خطة المواد حسب الصف والشعبة"""
    if grade in ("G7", "G8", "G9"):
        return PREP_SUBJECTS
    elif grade == "G10":
        return G10_SUBJECTS
    elif grade == "G11":
        if section == "1":
            return SCIENCE_11_SUBJECTS
        elif section == "4":
            return TECH_11_SUBJECTS
        else:
            return ARTS_11_SUBJECTS
    elif grade == "G12":
        if section == "1":
            return SCIENCE_12_SUBJECTS
        else:
            return ARTS_12_SUBJECTS
    return PREP_SUBJECTS


class Command(BaseCommand):
    help = "توزيع المواد على الفصول حسب أنصبة وزارة التربية قطر"

    def handle(self, *args, **options):
        school = School.objects.first()
        if not school:
            self.stderr.write("لا توجد مدرسة!")
            return

        year = settings.CURRENT_ACADEMIC_YEAR
        classes = ClassGroup.objects.filter(
            school=school, academic_year=year, is_active=True
        ).order_by("grade", "section")

        # تحميل المواد
        subjects = {s.name_ar: s for s in Subject.objects.filter(school=school)}

        created = 0
        skipped = 0
        errors = []

        for cls in classes:
            # تخطي فصول ESE
            if "ESE" in cls.section:
                self.stdout.write(f"  [SKIP] {cls} (ESE)")
                continue

            plan = get_subject_plan(cls.grade, cls.section)
            total = sum(plan.values())

            for subject_name, weekly in plan.items():
                subj = subjects.get(subject_name)
                if not subj:
                    errors.append(f"مادة غير موجودة: {subject_name}")
                    continue

                _, was_created = SubjectClassAssignment.objects.get_or_create(
                    class_group=cls,
                    subject=subj,
                    academic_year=year,
                    defaults={
                        "school": school,
                        "teacher": None,
                        "weekly_periods": weekly,
                        "requires_lab": subject_name in LAB_SUBJECTS,
                        "is_active": True,
                    },
                )
                if was_created:
                    created += 1
                else:
                    skipped += 1

            self.stdout.write(f"  {cls} -> {total} periods/week ({cls.grade}/{cls.section})")

        self.stdout.write(self.style.SUCCESS(
            f"\n[OK] {created} created | {skipped} skipped | {len(errors)} errors"
        ))
        if errors:
            for e in set(errors):
                self.stderr.write(f"  [!] {e}")

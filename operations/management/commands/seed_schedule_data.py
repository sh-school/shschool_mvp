"""
management command: إدخال البيانات الأساسية للجدولة الذكية
- TimeSlotConfig (7 حصص + استراحتين)
- المواد الدراسية (إعدادي + ثانوي)
"""

from django.core.management.base import BaseCommand
from django.conf import settings

from core.models import School
from operations.models import Subject, TimeSlotConfig


# ── توقيتات الحصص — وزارة التربية قطر 2025-2026 ──

REGULAR_SLOTS = [
    # (period, start, end, is_break, break_label)
    (1, "07:10", "07:55", False, ""),
    (2, "08:00", "08:45", False, ""),
    (3, "08:50", "09:35", False, ""),
    (100, "09:35", "09:55", True, "استراحة رئيسية"),  # 100+ = استراحات
    (4, "09:55", "10:40", False, ""),
    (5, "10:45", "11:30", False, ""),
    (101, "11:30", "11:45", True, "استراحة صلاة"),
    (6, "11:45", "12:30", False, ""),
    (7, "12:35", "13:20", False, ""),
]

THURSDAY_SLOTS = [
    (1, "07:10", "07:55", False, ""),
    (2, "08:00", "08:45", False, ""),
    (3, "08:50", "09:35", False, ""),
    (100, "09:35", "09:55", True, "استراحة رئيسية"),
    (4, "09:55", "10:40", False, ""),
    (5, "10:45", "11:30", False, ""),
    (101, "11:30", "11:45", True, "استراحة صلاة"),
    (6, "11:45", "12:30", False, ""),
]

RAMADAN_SLOTS = [
    (1, "09:00", "09:35", False, ""),
    (2, "09:40", "10:15", False, ""),
    (100, "10:15", "10:25", True, "استراحة"),
    (3, "10:25", "11:00", False, ""),
    (4, "11:05", "11:40", False, ""),
    (5, "11:45", "12:20", False, ""),
]

# ── المواد الدراسية ──

SUBJECTS = [
    # المواد المشتركة (إعدادي + ثانوي)
    ("اللغة العربية", "ARA"),
    ("اللغة الإنجليزية", "ENG"),
    ("الرياضيات", "MAT"),
    ("التربية الإسلامية", "ISL"),
    ("الدراسات الاجتماعية", "SOC"),
    ("الحوسبة وتكنولوجيا المعلومات", "ICT"),
    ("التربية البدنية", "PE"),
    ("المهارات الحياتية والمهنية", "LFS"),
    # إعدادي فقط
    ("العلوم", "SCI"),
    ("الفنون البصرية", "ART"),
    # ثانوي فقط
    ("الكيمياء", "CHM"),
    ("الفيزياء", "PHY"),
    ("الأحياء", "BIO"),
    # ثانوي آداب
    ("الرياضيات العامة", "GMH"),
    ("العلوم العامة", "GSC"),
    ("الجغرافيا", "GEO"),
    ("التاريخ", "HIS"),
]


class Command(BaseCommand):
    help = "إدخال بيانات الحصص الزمنية والمواد الدراسية"

    def handle(self, *args, **options):
        school = School.objects.first()
        if not school:
            self.stderr.write("لا توجد مدرسة في قاعدة البيانات!")
            return

        self.stdout.write(f"المدرسة: {school.name}")

        # ── TimeSlotConfig ──
        created_slots = 0
        for day_type, slots in [("regular", REGULAR_SLOTS), ("thursday", THURSDAY_SLOTS), ("ramadan", RAMADAN_SLOTS)]:
            for period, start, end, is_break, label in slots:
                _, created = TimeSlotConfig.objects.get_or_create(
                    school=school,
                    period_number=period,
                    day_type=day_type,
                    start_time=start,
                    defaults={
                        "end_time": end,
                        "is_break": is_break,
                        "break_label": label,
                    },
                )
                if created:
                    created_slots += 1

        self.stdout.write(self.style.SUCCESS(f"[OK] TimeSlotConfig: {created_slots} سجل جديد"))

        # ── المواد الدراسية ──
        created_subjects = 0
        for name, code in SUBJECTS:
            _, created = Subject.objects.get_or_create(
                school=school,
                name_ar=name,
                defaults={"code": code},
            )
            if created:
                created_subjects += 1

        self.stdout.write(self.style.SUCCESS(f"[OK] المواد الدراسية: {created_subjects} مادة جديدة"))
        self.stdout.write(self.style.SUCCESS("[OK] اكتمل إدخال البيانات الأساسية"))

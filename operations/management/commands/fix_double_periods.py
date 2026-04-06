"""
إصلاح الحصص المزدوجة المفقودة في قاعدة البيانات.
هذا الأمر يكتشف المواد ذات الحصتين المتتاليتين (ART, IT, CS, TECH)
التي فُقدت حصة منها بسبب merged cells في PDF aSc Timetables،
ثم يُنشئ الحصة المفقودة.
"""

from collections import defaultdict

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import transaction

from core.models import School
from operations.models import ScheduleSlot

# المواد ذات الحصتين المتتاليتين (TECH ليست مزدوجة — حصتان في أيام مختلفة)
DOUBLE_PERIOD_CODES = {"ART", "IT", "CS"}

# أوقات الحصص
from datetime import time

PERIOD_TIMES = {
    1: (time(7, 10), time(7, 55)),
    2: (time(8, 0), time(8, 45)),
    3: (time(8, 50), time(9, 35)),
    4: (time(9, 55), time(10, 40)),
    5: (time(10, 45), time(11, 30)),
    6: (time(11, 45), time(12, 30)),
    7: (time(12, 35), time(13, 20)),
}


class Command(BaseCommand):
    help = "إصلاح الحصص المزدوجة المفقودة (ART, IT, CS, TECH)"

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="عرض التغييرات فقط بدون تنفيذ",
        )

    def handle(self, *args, **options):
        import io
        import sys

        self.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", line_buffering=True)

        dry_run = options["dry_run"]
        school = School.objects.first()
        year = settings.CURRENT_ACADEMIC_YEAR

        self.stdout.write(self.style.WARNING("=" * 60))
        self.stdout.write(
            self.style.WARNING(f"  {'[DRY RUN] ' if dry_run else ''}fix_double_periods")
        )
        self.stdout.write(self.style.WARNING("=" * 60))

        # جلب كل الحصص
        all_slots = ScheduleSlot.objects.filter(
            school=school, academic_year=year, is_active=True
        ).select_related("subject", "teacher", "class_group")

        # فهرس: (class_group_id, day) -> {period: slot}
        class_day_map = defaultdict(dict)
        # فهرس: (teacher_id, class_group_id, subject_code, day) -> [period_numbers]
        double_subject_map = defaultdict(list)

        for slot in all_slots:
            cg_id = str(slot.class_group_id)
            class_day_map[(cg_id, slot.day_of_week)][slot.period_number] = slot

            if slot.subject.code in DOUBLE_PERIOD_CODES:
                key = (str(slot.teacher_id), cg_id, slot.subject.code, slot.day_of_week)
                double_subject_map[key].append(slot)

        # فهرس مشترك للحصص المحجوزة (يُحدَّث عند ملء حصة)
        global_occupied = defaultdict(set)
        for slot in all_slots:
            cg_id = str(slot.class_group_id)
            global_occupied[(cg_id, slot.day_of_week)].add(slot.period_number)

        # أيضاً فهرس المعلم لمنع تعارض معلم (معلم نفسه في نفس اليوم/الحصة)
        teacher_occupied = defaultdict(set)
        for slot in all_slots:
            teacher_occupied[(str(slot.teacher_id), slot.day_of_week)].add(slot.period_number)

        # كشف الحصص المفقودة — ترتيب: المواد الأقل حصصاً أولاً (IT/CS قبل ART)
        # هذا يضمن أن IT/CS تأخذ أولوية للحصص المتنافس عليها
        subject_total = defaultdict(int)
        for key, sl in double_subject_map.items():
            subject_total[key[2]] += len(sl)
        sorted_items = sorted(double_subject_map.items(), key=lambda x: subject_total[x[0][2]])

        to_create = []
        for key, slots_list in sorted_items:
            if len(slots_list) >= 2:
                continue  # موجودة كاملة

            teacher_id, cg_id, subj_code, day = key
            existing = slots_list[0]
            p = existing.period_number

            # حد الخميس
            grade_str = existing.class_group.grade.replace("G", "").replace("g", "")
            try:
                grade_num = int(grade_str)
            except (ValueError, TypeError):
                grade_num = 0
            max_period = 7
            if day == 4 and grade_num in (7, 8, 9):
                max_period = 6

            class_occupied = global_occupied[(cg_id, day)]
            teacher_busy = teacher_occupied[(teacher_id, day)]

            candidate = None
            # أولاً: الحصة السابقة
            if p - 1 >= 1 and (p - 1) not in class_occupied and (p - 1) not in teacher_busy:
                candidate = p - 1
            # ثانياً: الحصة التالية
            elif (
                p + 1 <= max_period
                and (p + 1) not in class_occupied
                and (p + 1) not in teacher_busy
            ):
                candidate = p + 1

            if candidate:
                start_t, end_t = PERIOD_TIMES[candidate]
                to_create.append(
                    {
                        "slot": ScheduleSlot(
                            school=school,
                            teacher_id=existing.teacher_id,
                            class_group_id=existing.class_group_id,
                            subject=existing.subject,
                            day_of_week=day,
                            period_number=candidate,
                            start_time=start_t,
                            end_time=end_t,
                            academic_year=year,
                            is_active=True,
                        ),
                        "info": (
                            f"{existing.subject.name_ar} ({subj_code}) | "
                            f"{existing.class_group} | "
                            f"Day {day} P{candidate} "
                            f"(adjacent to P{p}) | "
                            f"{existing.teacher.full_name}"
                        ),
                    }
                )
                # تحديث الفهارس لمنع التصادم مع حصص لاحقة
                global_occupied[(cg_id, day)].add(candidate)
                teacher_occupied[(teacher_id, day)].add(candidate)
            else:
                self.stdout.write(
                    self.style.WARNING(
                        f"  [!] لا يمكن ملء: {existing.subject.name_ar} "
                        f"({subj_code}) | {existing.class_group} | Day {day} P{p} — "
                        f"لا فارغة مجاورة"
                    )
                )

        # عرض النتائج
        self.stdout.write(f"\n  الحصص المزدوجة المفقودة: {len(to_create)}")

        DAY_NAMES = ["الأحد", "الاثنين", "الثلاثاء", "الأربعاء", "الخميس"]
        for item in to_create:
            self.stdout.write(f"  [+] {item['info']}")

        if dry_run:
            self.stdout.write(self.style.WARNING("\n  [DRY RUN] لم يتم تنفيذ أي تغيير"))
            return

        if not to_create:
            self.stdout.write(self.style.SUCCESS("\n  لا حصص مفقودة — كل شيء سليم"))
            return

        # تنفيذ
        with transaction.atomic():
            created = ScheduleSlot.objects.bulk_create(
                [item["slot"] for item in to_create],
                batch_size=100,
            )
            self.stdout.write(
                self.style.SUCCESS(f"\n  [OK] تم إنشاء {len(created)} حصة مزدوجة مفقودة")
            )

        # ملخص بعد الإصلاح
        self.stdout.write("\n  ملخص بعد الإصلاح:")
        for code in DOUBLE_PERIOD_CODES:
            count = ScheduleSlot.objects.filter(
                school=school, subject__code=code, academic_year=year, is_active=True
            ).count()
            self.stdout.write(f"    {code}: {count} slots")

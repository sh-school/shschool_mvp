"""مصالحةُ أوقات الحصص النشطة مع جرس نطاق شعبتها — idempotent.

    python manage.py resync_slot_times [--year 2026-2027] [--dry-run]

الحصّةُ تحمل وقتَها مكتوباً (`start_time`، `end_time`) يومَ تُولَّد. فإن
وُضعت النطاقاتُ بعد اعتماد الجدول — أو غُيّر الجرسُ بعده — بقيت الحصصُ على
الوقت القديم، وهو ما يُرى في الشاشة والورقة: الثانويُّ الخميسَ ينتهي 12:30
والحصّةُ تقول 13:20. هذا الأمرُ يعيد كتابةَ وقت كلّ حصّةٍ نشطةٍ من جرس نطاق
شعبتها ليومها، بترتيب البحث نفسِه الذي يكتب به المولّد (`bell_lookup`).

ولا يمسّ الجلسات؛ فالجلسةُ تُطابَق بالوقت، ولها `resync_sessions` لمدى
التواريخ بعد هذا الأمر.
"""

from django.core.management.base import BaseCommand
from django.db import transaction

from core.academic_calendar import academic_year_for_school
from core.models import School
from operations.models import ScheduleSlot
from operations.scheduler import bell_lookup


def _clock_overlaps(slots) -> list:
    """أزواجُ حصص المعلّم الواحد في اليوم الواحد التي تتداخل بالساعة.

    حصّتا اختيارٍ متزامنتان (الوقتُ نفسه) ليستا تداخلاً؛ والتماسُّ
    (نهايةٌ = بداية) مجازٌ.
    """
    by_teacher_day: dict = {}
    for slot in slots:
        by_teacher_day.setdefault((slot.teacher_id, slot.day_of_week), []).append(slot)
    found = []
    for (_, day), group in by_teacher_day.items():
        group.sort(key=lambda s: (s.start_time, s.end_time))
        for a, b in zip(group, group[1:], strict=False):
            if (a.start_time, a.end_time) == (b.start_time, b.end_time):
                continue
            if b.start_time < a.end_time:
                found.append((a.teacher, day, a, b))
    return found


class Command(BaseCommand):
    help = "إعادة كتابة أوقات الحصص النشطة من جرس نطاق شعبتها (الأحد–الأربعاء والخميس)"

    def add_arguments(self, parser):
        parser.add_argument("--year", help="العام الدراسيّ، وإلّا عامُ المدرسة الجاري")
        parser.add_argument("--dry-run", action="store_true", help="عرضٌ بلا كتابة")

    def handle(self, *args, **opts):
        total = updated = 0
        for school in School.objects.all():
            year = opts["year"] or academic_year_for_school(school)
            lookup = bell_lookup(school)
            with transaction.atomic():
                slots = list(
                    ScheduleSlot.objects.filter(
                        school=school, academic_year=year, is_active=True
                    ).select_related("class_group", "teacher")
                )
                changed = []
                for slot in slots:
                    start, end = lookup(
                        slot.day_of_week, slot.period_number, slot.class_group.time_band_id
                    )
                    if (slot.start_time, slot.end_time) != (start, end):
                        slot.start_time, slot.end_time = start, end
                        changed.append(slot)
                if changed:
                    ScheduleSlot.objects.bulk_update(changed, ["start_time", "end_time"])
                n = len(slots)
                total += n
                updated += len(changed)
                self.stdout.write(
                    f"== {school.name} ({year}): حصص={n} عُدّلت={len(changed)} "
                    f"مستوية={n - len(changed)}"
                )
                # جدولٌ اعتُمد قبل الحكم بالساعة (HC12) قد يجمع لمعلّمٍ حصّتين
                # تتداخلان بالساعة بعد المصالحة — والحلُّ توليدٌ جديد لا هذا الأمر.
                for teacher, day, a, b in _clock_overlaps(slots):
                    self.stdout.write(
                        self.style.WARNING(
                            f"   تداخلٌ بالساعة: {teacher} يوم {day} — "
                            f"ح{a.period_number} {a.start_time:%H:%M}-{a.end_time:%H:%M} × "
                            f"ح{b.period_number} {b.start_time:%H:%M}-{b.end_time:%H:%M}"
                        )
                    )
                if opts["dry_run"]:
                    transaction.set_rollback(True)
        tag = "DRY-RUN — لم يُكتب شيء" if opts["dry_run"] else "DONE"
        self.stdout.write(self.style.SUCCESS(f"{tag}: total={total} updated={updated}"))

"""بذرُ نطاقات التوقيت وأجراسها من «التوزيع الزمنيّ للحصص» — idempotent.

    python manage.py seed_time_bands [--dry-run]

المصدر: التوزيع الزمنيّ لليوم المدرسيّ 2025–2026 (أكتوبر)، مؤكَّدٌ ساريَ
العام 2026–2027 (قرار 2026-09-04). ثلاثةُ نطاقات:

  ground    الطابق الأرضيّ    (السابع، الثامن، تاسع/1)
  ninth     تاسع 2·3·4        (كالعلويّ من الأحد إلى الأربعاء، وله جرسُه الخميس)
  secondary الثانويّ          (العاشر إلى الثاني عشر)

الأمرُ يُنشئ النطاقاتِ وأوقاتَها ولا ينسب الشُّعب — النسبةُ قرارُ الإدارة من
لوحة الإدارة (الشُّعب → نطاق التوقيت). ويُحدّث ما تغيّر ويترك ما استوى.
"""

import datetime as dt

from django.core.management.base import BaseCommand
from django.db import transaction

from core.models import School, TimeBand
from operations.models import TimeSlotConfig


def t(h, m):
    return dt.time(h, m)


BANDS = [
    ("ground", "الطابق الأرضيّ (7، 8، 9/1)", 1),
    ("ninth", "التاسع 2·3·4", 2),
    ("secondary", "الثانويّ (10–12)", 3),
]

# (النطاق، نوع اليوم) → [(رقم أو 100+ للاستراحة، بداية، نهاية، اسم الاستراحة)]
UPPER_REGULAR = [
    (1, t(7, 10), t(8, 0), ""),
    (2, t(8, 0), t(8, 45), ""),
    (3, t(8, 45), t(9, 35), ""),
    (4, t(9, 35), t(10, 25), ""),
    (100, t(10, 25), t(10, 45), "الفسحة"),
    (5, t(10, 50), t(11, 35), ""),
    (6, t(11, 35), t(12, 25), ""),
    (7, t(12, 25), t(13, 10), ""),
    (101, t(13, 10), t(13, 30), "الصلاة"),
]

TIMES = {
    ("ground", "regular"): [
        (1, t(7, 10), t(8, 0), ""),
        (2, t(8, 0), t(8, 50), ""),
        (3, t(8, 50), t(9, 35), ""),
        (100, t(9, 35), t(9, 55), "الفسحة"),
        (4, t(10, 0), t(10, 50), ""),
        (5, t(10, 50), t(11, 35), ""),
        (6, t(11, 35), t(12, 20), ""),
        (101, t(12, 20), t(12, 40), "الصلاة"),
        (7, t(12, 40), t(13, 30), ""),
    ],
    ("ninth", "regular"): UPPER_REGULAR,
    ("secondary", "regular"): UPPER_REGULAR,
    ("ground", "thursday"): [
        (1, t(7, 10), t(8, 0), ""),
        (2, t(8, 0), t(8, 50), ""),
        (3, t(8, 50), t(9, 35), ""),
        (100, t(9, 35), t(9, 55), "الفسحة"),
        (4, t(10, 0), t(10, 50), ""),
        (5, t(10, 50), t(11, 35), ""),
        (101, t(11, 35), t(11, 55), "الصلاة"),
        (6, t(11, 55), t(12, 40), ""),
    ],
    ("ninth", "thursday"): [
        (1, t(7, 10), t(8, 0), ""),
        (2, t(8, 0), t(8, 50), ""),
        (3, t(8, 50), t(9, 35), ""),
        (100, t(9, 35), t(9, 55), "الفسحة"),
        (4, t(10, 0), t(10, 50), ""),
        (5, t(10, 50), t(11, 40), ""),
        (6, t(11, 40), t(12, 30), ""),
        (101, t(12, 30), t(12, 40), "الصلاة"),
    ],
    ("secondary", "thursday"): [
        (1, t(7, 10), t(7, 55), ""),
        (2, t(7, 55), t(8, 40), ""),
        (3, t(8, 40), t(9, 20), ""),
        (4, t(9, 20), t(10, 5), ""),
        (100, t(10, 5), t(10, 25), "الفسحة"),
        (5, t(10, 25), t(11, 10), ""),
        (6, t(11, 10), t(11, 50), ""),
        (7, t(11, 50), t(12, 30), ""),
        (101, t(12, 30), t(12, 45), "الصلاة"),
    ],
}


class Command(BaseCommand):
    help = "بذر نطاقات التوقيت الثلاثة وأجراسها (الأحد–الأربعاء والخميس) — idempotent"

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args, **opts):
        created = updated = unchanged = 0
        for school in School.objects.all():
            with transaction.atomic():
                bands = {}
                for code, name, order in BANDS:
                    band, was_created = TimeBand.objects.update_or_create(
                        school=school, code=code, defaults={"name": name, "order": order}
                    )
                    bands[code] = band
                for (code, day_type), rows in TIMES.items():
                    for number, start, end, label in rows:
                        obj, was_created = TimeSlotConfig.objects.get_or_create(
                            school=school,
                            band=bands[code],
                            day_type=day_type,
                            period_number=number,
                            defaults={
                                "start_time": start,
                                "end_time": end,
                                "is_break": number >= 100,
                                "break_label": label,
                            },
                        )
                        if was_created:
                            created += 1
                        elif (obj.start_time, obj.end_time, obj.is_break, obj.break_label) != (
                            start,
                            end,
                            number >= 100,
                            label,
                        ):
                            obj.start_time, obj.end_time = start, end
                            obj.is_break, obj.break_label = number >= 100, label
                            obj.save(
                                update_fields=["start_time", "end_time", "is_break", "break_label"]
                            )
                            updated += 1
                        else:
                            unchanged += 1
                self.stdout.write(
                    f"== {school.name}: النطاقات {', '.join(b.name for b in bands.values())}"
                )
                if opts["dry_run"]:
                    transaction.set_rollback(True)
        tag = "DRY-RUN — لم يُكتب شيء" if opts["dry_run"] else "DONE"
        self.stdout.write(
            self.style.SUCCESS(f"{tag}: created={created} updated={updated} unchanged={unchanged}")
        )

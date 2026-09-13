"""بذرُ نطاقات التوقيت وأجراسها من «التوزيع الزمنيّ للحصص» — idempotent.

    python manage.py seed_time_bands [--dry-run]

المصدر: التوزيع الزمنيّ لليوم المدرسيّ 2025–2026 (أكتوبر)، مؤكَّدٌ ساريَ
العام 2026–2027 (قرار 2026-09-04). ثلاثةُ نطاقاتٍ على **طابقين**:

  الطابق          الجرس       الشُّعب
  ─────────────   ─────────   ────────────────────────────────────
  الأرضيّ          ground      السابع · الثامن · تاسع/1 · تاسع/2
  الأوّل           ninth       تاسع 3 · تاسع 4
  الأوّل           secondary   العاشر إلى الثاني عشر

وجرسا الطابق الأوّل متطابقان حرفاً من الأحد إلى الأربعاء، ويفترقان يومَ
**الخميس**: تاسع 3·4 فسحتُهم بعد الثالثة وصلاتُهم آخرَ اليوم، والثانويُّ
فسحتُه بعد الرابعة وحصصُه أقصر. فاثنان قبل الخميس وثلاثةٌ فيه.

وتاسع/2 كان علويّاً حتّى 2026-09-09 فنُقل إلى الأرضيّ (قرار الإدارة). وفرقُ
النطاقين يومَ الخميس: الأرضيُّ صلاتُه بعد الخامسة ثمّ يعود لسادسته، وتاسع 3·4
فسحتُهم مع الأرضيّ بعد الثالثة وصلاتُهم بعد السادسة ثمّ يغادرون.

والنسبةُ كانت تُترك للوحة الإدارة، فبقيت قاعدةُ الإنتاج بلا نطاقٍ أرضيٍّ أصلاً
وعشرُ شُعبٍ تُطبع بجرسٍ ليس جرسَها — ٢٨٣ حصّةً صُحّحت يوم اكتُشف (2026-09-09).
فصارت مكتوبةً هنا، تُنفَّذ بـ`--assign` ويُعرض أثرُها قبل الكتابة.
"""

import datetime as dt

from django.core.management.base import BaseCommand
from django.db import transaction

from core.academic_calendar import academic_year_for_school
from core.models import ClassGroup, School, TimeBand
from operations.models import TimeSlotConfig


def t(h, m):
    return dt.time(h, m)


#: (الرمز، الاسم، الترتيب، الطابق)
#:
#: والطابقُ محفوظٌ لا مشتقٌّ من الرمز: `ninth` و`secondary` كلاهما في الطابق
#: الأوّل، وبلا حقلٍ يقول ذلك يتعذّر السؤالُ «ما يرنّه الطابقُ الأوّلُ الآن؟»
#: إلّا بتسميةِ رموزٍ في الكود — تسميةٌ تكذب في أوّل جرسٍ يُضاف.
BANDS = [
    ("ground", "الطابق الأرضيّ (7، 8، 9/1، 9/2)", 1, "ground"),
    ("ninth", "التاسع 3·4 (الطابق الأوّل)", 2, "first"),
    ("secondary", "الثانويّ 10–12 (الطابق الأوّل)", 3, "first"),
]

#: الصفُّ (وقسمُه في التاسع) → رمزُ النطاق. وما لا يُطابق يُترك على حاله
#: ويُسمّى في التقرير — كشعبة التربية الخاصّة، لا قرارَ فيها بعد.
ASSIGN_BY_GRADE = {
    "G7": "ground",
    "G8": "ground",
    "G10": "secondary",
    "G11": "secondary",
    "G12": "secondary",
}
ASSIGN_NINTH_SECTION = {"1": "ground", "2": "ground", "3": "ninth", "4": "ninth"}


def band_for(klass) -> str:
    """رمزُ النطاق لهذه الشعبة — أو `""` لمن يُترك على حاله."""
    if klass.grade == "G9":
        return ASSIGN_NINTH_SECTION.get(klass.section.rsplit("/", 1)[-1], "")
    return ASSIGN_BY_GRADE.get(klass.grade, "")


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
        parser.add_argument(
            "--assign",
            action="store_true",
            help="انسب الشُّعبَ إلى نطاقاتها أيضاً — ومن لا قاعدةَ له يُترك ويُسمّى",
        )

    def handle(self, *args, **opts):
        created = updated = unchanged = 0
        for school in School.objects.all():
            with transaction.atomic():
                bands = {}
                for code, name, order, floor in BANDS:
                    band, was_created = TimeBand.objects.update_or_create(
                        school=school,
                        code=code,
                        defaults={"name": name, "order": order, "floor": floor},
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
                if opts["assign"]:
                    moved, left = self._assign(school, bands)
                    for line in moved:
                        self.stdout.write(f"   → {line}")
                    for line in left:
                        self.stdout.write(f"   · يُترك على حاله: {line}")
                    self.stdout.write(f"   نُسبت {len(moved)} شعبة، وتُركت {len(left)}.")
                if opts["dry_run"]:
                    transaction.set_rollback(True)
        tag = "DRY-RUN — لم يُكتب شيء" if opts["dry_run"] else "DONE"
        self.stdout.write(
            self.style.SUCCESS(f"{tag}: created={created} updated={updated} unchanged={unchanged}")
        )

    def _assign(self, school, bands):
        """ينسب الشُّعبَ إلى نطاقاتها — ويُرجع (ما نُقل، ما تُرك)."""
        year = academic_year_for_school(school)
        moved, left = [], []
        for klass in (
            ClassGroup.objects.filter(school=school, academic_year=year, is_active=True)
            .select_related("time_band")
            .in_school_order()
        ):
            code = band_for(klass)
            now = klass.time_band.code if klass.time_band_id else "—"
            if not code:
                left.append(f"{klass.short_code} (نطاقُه الآن: {now})")
            elif now != code:
                ClassGroup.objects.filter(pk=klass.pk).update(time_band=bands[code])
                moved.append(f"{klass.short_code}: {now} ← {code}")
        return moved, left

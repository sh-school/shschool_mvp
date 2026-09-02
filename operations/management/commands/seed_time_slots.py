"""أوقاتُ الحصص تُقرأ من الجدول القائم، ولا تُخترع.

`TimeSlotConfig` فارغٌ في هذه المدرسة، فالمولّدُ يقع على أوقاتٍ مدفونةٍ في
الكود (7:10 → 13:10). وقد تصادف أن تكون صحيحة، لكنّ «تصادف» ليست مصدراً:
لو اختلف جرسُ المدرسة عنها لكُتب الخطأُ في ثمانمئةٍ وسبعين صفّاً بلا أن يشتكي
أحد.

والجدولُ القائمُ يحمل الوقتَ الحقيقيَّ في كلّ صفّ. فيُقرأ منه ما هو **الأكثرُ
شيوعاً** لكلّ (نوع يوم · رقم حصّة)، ويُكتب في الإعدادات. أي أنّ المصدرَ هو
واقعُ المدرسة لا اجتهادُ مبرمج.

    python manage.py seed_time_slots --school SHH --year 2026-2027
    python manage.py seed_time_slots --school SHH --dry-run
"""

from collections import Counter, defaultdict

from django.core.management.base import BaseCommand, CommandError

from core.models import School
from operations.models import ScheduleSlot, TimeSlotConfig

THURSDAY = 4


class Command(BaseCommand):
    help = "يملأ TimeSlotConfig من أوقات الجدول القائم — لا من قيمٍ مخترعة."

    def add_arguments(self, parser):
        parser.add_argument("--school", default="SHH")
        parser.add_argument("--year", default="")
        parser.add_argument("--dry-run", action="store_true", help="اعرض ولا تكتب")

    def handle(self, *args, **opts):
        school = School.objects.filter(code=opts["school"]).first()
        if school is None:
            raise CommandError(f"لا مدرسةَ بالكود {opts['school']}")
        year = opts["year"] or self._year(school)

        rows = ScheduleSlot.objects.filter(
            school=school, academic_year=year, is_active=True
        ).values_list("day_of_week", "period_number", "start_time", "end_time")
        if not rows:
            raise CommandError(f"لا حصصَ نشطةً في {year} — لا مصدرَ للأوقات.")

        seen = defaultdict(Counter)
        for day, period, start, end in rows:
            day_type = "thursday" if day == THURSDAY else "regular"
            seen[(day_type, period)][(start, end)] += 1

        written = 0
        for (day_type, period), times in sorted(seen.items()):
            (start, end), _ = times.most_common(1)[0]
            spread = f" (من {sum(times.values())} حصّة، وفيها {len(times)} توقيتاً مختلفاً)"
            self.stdout.write(
                f"{day_type} · ح{period}: {start:%H:%M} → {end:%H:%M}"
                + (spread if len(times) > 1 else "")
            )
            if opts["dry_run"]:
                continue
            TimeSlotConfig.objects.update_or_create(
                school=school,
                period_number=period,
                day_type=day_type,
                defaults={"start_time": start, "end_time": end, "is_break": False},
            )
            written += 1

        if opts["dry_run"]:
            self.stdout.write(self.style.WARNING("عرضٌ فقط — لم يُكتب شيء."))
        else:
            self.stdout.write(self.style.SUCCESS(f"كُتب {written} توقيتاً من واقع الجدول."))

    def _year(self, school):
        from core.academic_calendar import academic_year_for_school

        return academic_year_for_school(school)

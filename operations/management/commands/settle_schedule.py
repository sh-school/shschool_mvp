"""سدادُ الجدول الحيّ بأقلّ اضطراب (SCH-06) — مسودّةٌ جديدةٌ لا نشر.

    python manage.py settle_schedule --dry-run          # الفرقُ والمخالفاتُ قبل وبعد، بلا كتابة
    python manage.py settle_schedule                    # يكتب مسودّةً حصصُها مطفأة
    ... [--school SHH] [--year 2026-2027] [--budget 240]

يُحمَّل الجدولُ المعتمدُ كما هو، ويُسدَّد ما كُسر فيه برخصة (`scheduler_settle`)، ويُعرض
عددُ المخالفات بكلّ رمزٍ قبل السداد وبعده والخاناتُ التي تغيّرت. والكتابةُ مسودّةٌ جديدة:
الحصصُ الحيّةُ لا تُمَسّ، والاعتمادُ من صفحة الجدول الذكيّ بعد الدوام — كأيّ توليد.
"""

from typing import Any

from django.core.management.base import BaseCommand, CommandError, CommandParser

from core.academic_calendar import academic_year_for_school
from core.models import School
from operations.scheduler import DAY_NAMES
from operations.scheduler_live import LiveScheduleError, settle_live

#: أسماءُ حركات السداد كما تُقرأ — والحركةُ بلا اسمٍ هنا تُطبع برمزها لا تُسقط.
MOVE_NAMES = {
    "move": "نقل",
    "swap": "تبديل",
    "chain": "سلسلة",
    "eject": "إزاحة",
    "eject_deep": "إزاحةٌ عميقة",
}


class Command(BaseCommand):
    help = "يسدّد مخالفاتِ الجدول الحيّ ويكتبها مسودّةً — أو يعرض الفرقَ بـ--dry-run"

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("--school", default="", help="رمزُ المدرسة — والافتراضُ الأولى")
        parser.add_argument("--year", default="", help="العامُ الدراسيّ — والافتراضُ الجاري")
        parser.add_argument("--dry-run", action="store_true", help="اعرض الفرقَ ولا تكتب")
        parser.add_argument(
            "--budget", type=float, default=240.0, help="سقفُ زمن السداد بالثواني (240)"
        )

    def handle(self, *args: Any, **opts: Any) -> None:
        school = self._school(opts["school"])
        year = opts["year"] or academic_year_for_school(school)
        try:
            outcome = settle_live(
                school, year, budget=opts["budget"], dry_run=opts["dry_run"], user=None
            )
        except LiveScheduleError as exc:
            raise CommandError(str(exc)) from exc
        self._report(school, year, outcome)

        generation = outcome["generation"]
        if opts["dry_run"]:
            self.stdout.write(self.style.WARNING("\nعرضٌ فقط — بلا --dry-run تُكتب مسودّة."))
        elif generation is None:
            self.stdout.write(self.style.WARNING("\nلا خانةَ تغيّرت — لم تُكتب مسودّة."))
        else:
            self.stdout.write(
                self.style.SUCCESS(
                    f"\nكُتبت المسودّة {str(generation.id)[:8]} — حصصُها مطفأة، والحيُّ كما هو. "
                    "اعتمدها من صفحة الجدول الذكيّ بعد الدوام."
                )
            )

    def _report(self, school: School, year: str, outcome: dict) -> None:
        before, after = outcome["before"], outcome["after"]
        source = outcome["source"]
        origin = f"التوليد {str(source.id)[:8]}" if source else "بلا توليدٍ معتمد"
        self.stdout.write(f"== {school.name} — {year} — {origin} — {outcome['slots']} حصّةً حيّة")

        self.stdout.write("المخالفات (قبل ← بعد):")
        for code in sorted(before["by_code"].keys() | after["by_code"].keys()):
            was, now = before["by_code"].get(code, 0), after["by_code"].get(code, 0)
            self.stdout.write(f"  {code:<6} {was:>4} ← {now}")
        self.stdout.write(f"  {'الكلّ':<6} {before['count']:>4} ← {after['count']}")

        settlement = outcome["settlement"]
        moves = " · ".join(
            f"{MOVE_NAMES.get(kind, kind)} {count}"
            for kind, count in settlement.get("moves", {}).items()
        )
        self.stdout.write(f"الحركات: {moves} — في {outcome['elapsed_ms'] / 1000:.1f} ث")
        if settlement.get("timed_out"):
            self.stdout.write(
                self.style.WARNING("انتهى الموعدُ قبل أن يفرغ السداد — ارفع --budget لمزيد.")
            )

        changes = outcome["changes"]
        self.stdout.write(f"\nالخانات المتغيّرة ({len(changes)}):")
        for row in changes:
            self.stdout.write(
                f"  {row['class']} · {DAY_NAMES[row['day']]} · ح{row['period']}: "
                f"{row['before'] or 'فراغ'} ← {row['after'] or 'فراغ'}"
            )

        if after["items"]:
            self.stdout.write(f"\nما بقي ({after['count']}):")
            for item in after["items"]:
                self.stdout.write(
                    f"  {item['code']} · {item['class']} · {item['subject']} · "
                    f"{DAY_NAMES[item['day']]} ح{item['period']} ({item['teacher']})"
                )

    def _school(self, code: str) -> School:
        school = (
            (School.objects.filter(code=code) if code else School.objects.all())
            .order_by("id")
            .first()
        )
        if school is None:
            raise CommandError(f"لا مدرسةَ برمز {code}" if code else "لا مدرسةَ في القاعدة")
        return school

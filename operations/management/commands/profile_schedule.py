"""
يقيس الجدولَ القائم ويُخرج تقريرَ الأساس — ولا يكتب شيئاً.

    python manage.py profile_schedule --year 2026-2027 [--json تقرير.json]

الجدولُ المستورد مخرجُ قراراتٍ إداريّةٍ اتُّخذت فعلاً، فهو أصدقُ ما نملك عن
قواعد المدرسة. وهذا الأمرُ يستخرج منه الأرقام ويعرض ما يستحقّ قراراً — ولا
يتّخذه: كلُّ سياسةٍ يقترحها موسومةٌ بأنّها **بحاجة إلى اعتماد**.

ولا رايةَ `--apply` هنا: ليس له مسارُ كتابةٍ أصلاً.
"""

import json

from django.core.management.base import BaseCommand, CommandError

from operations import schedule_profile as profiler


class Command(BaseCommand):
    help = "يقيس الجدول القائم ويُخرج تقرير الأساس (قراءةً فقط)"

    def add_arguments(self, parser):
        parser.add_argument("--year", required=True, help="مثال: 2026-2027")
        parser.add_argument("--school", default=None, help="كود المدرسة")
        parser.add_argument("--json", default="", help="يحفظ التقرير المفصَّل")
        parser.add_argument("--top", type=int, default=8, help="كم صفّاً يُعرض في كلّ قائمة")

    def handle(self, *args, **options):
        school = self._school(options["school"])
        year = options["year"]
        lessons = profiler.load_lessons(school, year)
        if not lessons:
            raise CommandError(f"لا حصصَ نشطةً في {year} — لا شيءَ يُقاس.")

        teachers = profiler.profile_teachers(lessons)
        sections = profiler.profile_sections(lessons)
        subjects = profiler.profile_subjects(lessons)
        fair = profiler.fairness(teachers)
        free_days = profiler.profile_availability(lessons)
        found = profiler.observations(lessons, teachers, sections, fair)

        w = self.stdout.write
        top = options["top"]

        w(f"\n{school.name} · العام {year}")
        w("═" * 64)
        w(f"  حصصٌ مرصودة: {len(lessons)}")
        w(f"  معلّمون: {len(teachers)}   شُعب: {len(sections)}   موادّ: {len(subjects)}")

        w("\n── عبءُ المعلّمين (أعلى " + str(top) + ") ──")
        w(f"  {'المعلّم':<28}{'أسبوعيّ':>8}{'أيّام':>7}{'أقصى/يوم':>10}{'فراغ':>7}{'تتابع':>7}")
        for p in teachers[:top]:
            w(
                f"  {p.name[:27]:<28}{p.weekly:>8}{p.days_used:>7}"
                f"{p.max_daily:>10}{p.gaps:>7}{p.longest_run:>7}"
            )

        w("\n── العدالة: التوزيع لا المتوسّط ──")
        for key, label in (
            ("weekly", "النصاب الأسبوعيّ"),
            ("max_daily", "أقصى حملٍ يوميّ"),
            ("gaps", "الفراغات"),
            ("first_period", "أيّامٌ تبدأ بالحصّة الأولى"),
            ("late_periods", "حصصٌ متأخّرة (٦ فأعلى)"),
            ("days_used", "أيّامُ العمل"),
            ("longest_run", "أطولُ تتابع"),
        ):
            s = fair[key]
            w(f"  {label:<28} أدنى {s['min']:>4} · وسيط {s['median']:>6} · أعلى {s['max']:>4}")

        w("\n── الشُّعب ──")
        w(f"  {'الشعبة':<26}{'مرحلة':>8}{'أسبوعيّ':>9}{'تكرار/يوم':>11}{'متجاور':>9}")
        for s in sections[:top]:
            w(
                f"  {s.name[:25]:<26}{s.level_type or '—':>8}{s.weekly:>9}"
                f"{s.twice_in_a_day:>11}{s.adjacent_pairs:>9}"
            )

        w("\n── المواد: أين تقع في اليوم ──")
        w(f"  {'المادّة':<26}{'حصص':>7}{'صباحيّ %':>10}{'في السابعة':>12}")
        for name, data in list(subjects.items())[:top]:
            w(
                f"  {name[:25]:<26}{data['total']:>7}{data['morning_share']:>10}{data['in_last_period']:>12}"
            )

        if free_days:
            w(f"\n── معلّمون لا يظهرون في يومٍ كامل ({len(free_days)}) ──")
            for name, days in list(free_days.items())[:top]:
                w(f"  {name[:30]:<32}{'، '.join(days)}")
            w("  (قد يكون إعفاءً رسميّاً وقد يكون أثرَ الجدول — لا يُسمّى إعفاءً بلا سند)")

        w("\n" + "═" * 64)
        w("  ما يستحقّ قراراً — ولا يُتّخذ هنا")
        w("═" * 64)
        for i, o in enumerate(found, start=1):
            w(f"\n  [{i}] FACT              {o.fact}")
            w(f"      OBSERVED PATTERN  {o.pattern}")
            w(f"      CANDIDATE POLICY  {o.candidate}")
            w(
                "      NEEDS APPROVAL    " + self.style.WARNING("نعم — لا تسري حتى تُعتمد")
                if o.needs_approval
                else "      NEEDS APPROVAL    لا"
            )

        if options["json"]:
            self._dump(
                options["json"], school, year, lessons, teachers, sections, subjects, fair, found
            )
            w(self.style.SUCCESS(f"\nحُفظ التقرير: {options['json']}"))

        w(self.style.SUCCESS("\nقراءةٌ فقط — لم يُكتب شيء.\n"))

    # ── مساعدات ──────────────────────────────────────────────────────

    def _school(self, code):
        from core.models import School

        if code:
            try:
                return School.objects.get(code=code)
            except School.DoesNotExist as exc:
                raise CommandError(f"لا مدرسة بهذا الكود: {code}") from exc
        schools = list(School.objects.all()[:2])
        if len(schools) != 1:
            raise CommandError("أكثرُ من مدرسة — حدّد --school بالكود.")
        return schools[0]

    def _dump(self, path, school, year, lessons, teachers, sections, subjects, fair, found):
        from dataclasses import asdict

        payload = {
            "school": school.name,
            "academic_year": year,
            "lessons": len(lessons),
            "fairness": fair,
            "teachers": [asdict(p) for p in teachers],
            "sections": [asdict(s) for s in sections],
            "subjects": subjects,
            "observations": [asdict(o) for o in found],
        }
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=1, default=str)

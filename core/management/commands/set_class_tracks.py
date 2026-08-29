"""
يضع مسار كل شعبةٍ ثانوية — «11/1=علمي» وأخواتها.

الشُّعب في القاعدة مُرقَّمةٌ `1 2 3 4` لا مُسمّاةً بمسارها، فلا يعرف النظام
أيّها العلميّ وأيّها الأدبيّ. وهذا الأمر يُدخل المطابقة دفعةً واحدة بدل ثمانِ
إدخالاتٍ يدوية.

والمطابقة تُمرَّر في السطر ولا تُكتب في الشيفرة: توزيع الشُّعب على المسارات
يتغيّر كل عام، وما يُخبَز اليوم يصير كذبةً في العام القادم.

    python manage.py set_class_tracks --year 2025-2026 \\
        --map 11/1=علمي 11/2=آداب 11/3=آداب 11/4=تكنولوجي \\
              12/1=علمي 12/2=آداب 12/3=آداب 12/4=آداب

ولا يكتب شيئاً بلا `--apply`: يعرض ما سيفعل ثم يقف.
"""

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from core.academic_calendar import academic_year_for_school
from core.models import ClassGroup, School

#: تُقارن بها الاختبارات بدل إعادة كتابتها — و«للحادي» لا تحوي «الحادي»
#: حرفياً، فلامُ الجرّ تلتحم بأداة التعريف. ودعوى تبحث عن نصٍّ أعادت كتابته
#: تسقط على فرقٍ لا تراه العين.
UNTRACKED_GRADE_MESSAGE = "المسار للحادي عشر والثاني عشر وحدهما"

#: أسماءٌ عربية مختصرة تُقبل إلى جانب المفاتيح — فمن يكتب المطابقة بشرٌ.
ALIASES = {
    "علمي": "science",
    "science": "science",
    "آداب": "humanities",
    "اداب": "humanities",
    "آداب وإنسانيات": "humanities",
    "اداب وانسانيات": "humanities",
    "انسانيات": "humanities",
    "humanities": "humanities",
    "تكنولوجي": "technology",
    "technology": "technology",
}


class Command(BaseCommand):
    help = "يضع مسار الشُّعب الثانوية من مطابقةٍ مثل 11/1=علمي"

    def add_arguments(self, parser):
        parser.add_argument("--year", default=None, help="افتراضياً العام الجاري")
        parser.add_argument("--school", default=None, help="كود المدرسة")
        parser.add_argument(
            "--map",
            nargs="+",
            required=True,
            metavar="صف/شعبة=مسار",
            help="مثال: 11/1=علمي 11/4=تكنولوجي",
        )
        parser.add_argument(
            "--apply",
            action="store_true",
            help="بدونه يعرض ما سيفعل ولا يكتب",
        )

    def handle(self, *args, **options):
        school = self._school(options["school"])
        year = options["year"] or academic_year_for_school(school)
        pairs = [self._parse(item) for item in options["map"]]

        self.stdout.write(f"\n{school.name} · العام {year}")
        self.stdout.write("═" * 52)

        planned, problems = [], []
        for grade, section, track in pairs:
            group = ClassGroup.objects.filter(
                school=school, academic_year=year, grade=grade, section=section
            ).first()
            label = f"{grade[1:]}/{section}"
            if group is None:
                problems.append(f"  {label:10} لا شعبة بهذا الاسم في {year}")
                continue
            if grade not in ClassGroup.TRACKED_GRADES:
                problems.append(f"  {label:10} {UNTRACKED_GRADE_MESSAGE}")
                continue
            planned.append((group, track, label))

        for group, track, label in planned:
            before = group.get_track_display() if group.track else "—"
            after = dict(ClassGroup.TRACKS)[track]
            mark = " (لا تغيير)" if group.track == track else ""
            self.stdout.write(f"  {label:10} {before:16} → {after}{mark}")

        if problems:
            self.stdout.write("\nما تعذّر:")
            for p in problems:
                self.stdout.write(p)

        if not options["apply"]:
            self.stdout.write(f"\nعرضٌ فقط — {len(planned)} شعبة. أضف --apply للكتابة.\n")
            return

        if problems:
            raise CommandError("لن أكتب شيئاً وفي المطابقة ما تعذّر — صحّحها أوّلاً.")

        with transaction.atomic():
            changed = 0
            for group, track, _label in planned:
                if group.track != track:
                    group.track = track
                    group.full_clean()
                    group.save(update_fields=["track"])
                    changed += 1

        self.stdout.write(f"\nكُتبت {changed} شعبة من {len(planned)}.\n")

    # ── مساعدات ──────────────────────────────────────────────────────

    def _school(self, code):
        school = School.objects.filter(code=code).first() if code else School.objects.first()
        if school is None:
            raise CommandError("لا مدرسة بهذا الكود.")
        return school

    def _parse(self, item):
        """«11/1=علمي» → ("G11", "1", "science")."""
        if "=" not in item:
            raise CommandError(f"صيغة غير مفهومة: {item} — المتوقَّع 11/1=علمي")
        name, _, track_raw = item.partition("=")
        track = ALIASES.get(track_raw.strip())
        if track is None:
            raise CommandError(
                f"مسار غير معروف: {track_raw} — المقبول: علمي، آداب وإنسانيات، تكنولوجي"
            )
        if "/" not in name:
            raise CommandError(f"اسم شعبة غير مفهوم: {name} — المتوقَّع 11/1")
        grade_num, _, section = name.strip().partition("/")
        return f"G{grade_num.strip()}", section.strip(), track

"""
يُنشئ شُعب عامٍ دراسيّ من قائمةٍ تُمرَّر في السطر.

    python manage.py create_year_sections --year 2026-2027 \\
        --sections 7/1 7/2 7/3 7/4 \\
                   8/1 8/2 8/3 8/4 8/5 \\
                   9/1 9/2 9/3 9/4 \\
                   10/1 10/2 10/3 10/4 \\
                   11/1=علمي 11/2=آداب 11/3=آداب 11/4=تكنولوجي \\
                   12/1=علمي 12/2=آداب 12/3=آداب 12/4=تكنولوجي

الشعبة بلا `=` تُنشأ بلا مسار — وهو حال السابع إلى العاشر. والمرحلة تُشتقّ من
الصف (٧–٩ إعدادي، ١٠–١٢ ثانوي) فلا تُكتب مرّتين.

ولا يكتب شيئاً بلا `--apply`: يعرض ما سيُنشئ وما هو قائمٌ أصلاً، ثم يقف.
وهو مُعاوِد: تشغيلُه ثانيةً لا يُنشئ نسخةً ثانية.
"""

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from core.management.commands.set_class_tracks import ALIASES
from core.models import ClassGroup, School

#: المرحلة من الصف — لا تُكتب في السطر لأنها مشتقّةٌ منه.
PREP_GRADES = ("G7", "G8", "G9")


class Command(BaseCommand):
    help = "يُنشئ شُعب عامٍ دراسيّ من قائمةٍ مثل 7/1 11/4=تكنولوجي"

    def add_arguments(self, parser):
        parser.add_argument("--year", required=True, help="مثال: 2026-2027")
        parser.add_argument("--school", default=None, help="كود المدرسة")
        parser.add_argument(
            "--sections",
            nargs="+",
            required=True,
            metavar="صف/شعبة[=مسار]",
            help="مثال: 7/1 8/2 11/4=تكنولوجي",
        )
        parser.add_argument("--apply", action="store_true", help="بدونه يعرض ولا يكتب")

    def handle(self, *args, **options):
        school = self._school(options["school"])
        year = options["year"]
        specs = [self._parse(s) for s in options["sections"]]
        self._reject_duplicates(specs)

        self.stdout.write(f"\n{school.name} · العام {year}")
        self.stdout.write("═" * 52)

        existing = {
            (g.grade, g.section): g
            for g in ClassGroup.objects.filter(school=school, academic_year=year)
        }

        to_create, already = [], []
        for grade, section, track in specs:
            label = f"{grade[1:]}/{section}"
            found = existing.get((grade, section))
            if found is None:
                to_create.append((grade, section, track, label))
            else:
                already.append((found, track, label))

        for _grade, _section, track, label in to_create:
            name = dict(ClassGroup.TRACKS)[track] if track else "—"
            self.stdout.write(f"  + {label:10} {name}")
        for group, track, label in already:
            same = (group.track or "") == (track or "")
            note = (
                "قائمة" if same else f"قائمة — المسار سيتغيّر إلى {dict(ClassGroup.TRACKS)[track]}"
            )
            self.stdout.write(f"  · {label:10} {note}")

        self.stdout.write(f"\nستُنشأ {len(to_create)} · قائمة {len(already)}")

        if not options["apply"]:
            self.stdout.write("عرضٌ فقط. أضف --apply للكتابة.\n")
            return

        with transaction.atomic():
            created = 0
            for grade, section, track, _label in to_create:
                group = ClassGroup(
                    school=school,
                    grade=grade,
                    section=section,
                    level_type="prep" if grade in PREP_GRADES else "sec",
                    track=track,
                    academic_year=year,
                )
                group.full_clean()
                group.save()
                created += 1

            updated = 0
            for group, track, _label in already:
                if (group.track or "") != (track or ""):
                    group.track = track
                    group.full_clean()
                    group.save(update_fields=["track"])
                    updated += 1

        self.stdout.write(f"\nأُنشئت {created} · عُدّلت {updated}\n")

    # ── مساعدات ──────────────────────────────────────────────────────

    def _school(self, code):
        school = School.objects.filter(code=code).first() if code else School.objects.first()
        if school is None:
            raise CommandError("لا مدرسة بهذا الكود.")
        return school

    def _reject_duplicates(self, specs):
        """شعبةٌ مذكورةٌ مرّتين تعني خطأً في القائمة لا نيّةً."""
        seen, dupes = set(), []
        for grade, section, _track in specs:
            key = (grade, section)
            if key in seen:
                dupes.append(f"{grade[1:]}/{section}")
            seen.add(key)
        if dupes:
            raise CommandError(f"شُعبٌ مكرّرة في القائمة: {', '.join(dupes)}")

    def _parse(self, item):
        """«11/4=تكنولوجي» → ("G11", "4", "technology")؛ و«7/1» → ("G7", "1", "")."""
        name, sep, track_raw = item.partition("=")
        track = ""
        if sep:
            track = ALIASES.get(track_raw.strip(), "")
            if not track:
                raise CommandError(
                    f"مسار غير معروف: {track_raw} — المقبول: علمي، آداب وإنسانيات، تكنولوجي"
                )
        if "/" not in name:
            raise CommandError(f"اسم شعبة غير مفهوم: {name} — المتوقَّع 7/1")
        grade_num, _, section = name.strip().partition("/")
        if not grade_num.strip().isdigit():
            raise CommandError(f"رقم صفٍّ غير مفهوم: {name}")
        return f"G{grade_num.strip()}", section.strip(), track

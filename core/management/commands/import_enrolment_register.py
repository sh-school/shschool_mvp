"""
يقيّد طلاب العام من «سجلّ القيد» الرسميّ الصادر عن النظام الوزاريّ.

    python manage.py import_enrolment_register "سجل_القيد.xlsx" \\
        --year 2026-2027 [--create-missing] [--fix-tracks] [--apply]

الملفُّ يقول بالاسم أين يجلس كلُّ طالبٍ هذا العام، فلا حاجة إلى محرّك ترفيعٍ
يجتهد: قواعدُ الترفيع طُبِّقت في الوزارة، وهذا مخرجُها. ومن كان في خانة شعبته
«‑» فقرارُه لم يُتّخذ بعد — يُعرَض ولا يُقيَّد.

بنيةُ الملفّ: ورقةٌ لكلّ صفّ («الصف- 07») وورقةٌ لكلّ شعبة، ورؤوسُها في السطر
الثالث. وأوراقُ الصفوف هي المرجع لأنّها تضمّ من لا شعبةَ له.

**ولا يُؤخَذ المسارُ من هذا الملفّ.** أسماءُ أوراقه تكتب «11-2-Technology»
و«11-4-Humanities»، والجدولُ المدرسيّ يقول عكسَه: 11/4 و12/4 وحدهما فيهما
علومُ الحاسب وتكنولوجيا المعلومات. فالمسارُ يُضبط بـ`set_class_tracks` ويُقاس
بما يُدرَّس فعلاً، وهذا الأمر يُنبّه على الخلاف ولا يكتبه.

**وترقيمُ الشُّعب قد يختلف بين السجلّ والمدرسة.** في الثاني عشر يضع السجلُّ
سبعةَ طلاب التكنولوجي في «12/2» وتسمّيهم المدرسة «12/4»، فتُمرَّر المطابقةُ
في `--map` صريحةً: بلا تخمينٍ ولا اشتقاقٍ من الأعداد.

ولا يمسّ من كان في المنصّة وليس في السجلّ: خرّيجٌ أو منتقلٌ، وإغلاقُ قيده
قرارٌ إداريٌّ لا يُتّخذ من سطر أوامر — يُعرَض عددُهم وحدَه.

ولا يكتب شيئاً بلا `--apply`.
"""

import re
from collections import Counter

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from core.models import ClassGroup, CustomUser, School
from core.models.academic import StudentEnrollment

#: رؤوسُ الجدول في السطر الثالث، فالبياناتُ تبدأ من الرابع.
FIRST_DATA_ROW = 4

#: صفٌّ مقبول: رقمٌ شخصيٌّ قطريٌّ من إحدى عشرة خانة.
NATIONAL_ID = re.compile(r"^\d{11}$")

#: «07/1» و«08/ESE» — والشعبةُ ما بعد الشرطة المائلة.
SECTION_LABEL = re.compile(r"^(\d{1,2})/(.+)$")


def canonical(label):
    """صيغةٌ واحدة للشعبة يتّفق عليها الملفُّ والقاعدة.

    السجلُّ يكتب «07/1» بصفرٍ بادئ، و`ClassGroup` يحفظ `G7` فيُنتج «7/1».
    والمقارنةُ بينهما نصّاً تجعل كلَّ شُعب السابع إلى التاسع «مفقودة»،
    فيُعاد إنشاؤها فوق القائم — وهو ما كشفه أوّلُ تشغيلٍ جافّ.
    """
    match = SECTION_LABEL.match(label)
    if not match:
        return label
    grade, section = match.groups()
    return f"{int(grade)}/{section.strip()}"


#: ما يكتبه النظامُ الوزاريّ لمن لم تُحدَّد شعبتُه بعد.
NO_SECTION = "-"

#: المسارُ في اسم ورقة الشعبة: «الشعبة الصفية- 11-2-Technology-».
SHEET_TRACK = re.compile(r"-\s*(\d{2})-(\S+?)-(Science|Technology|Humanities)-?\s*$")

TRACKS = {"Science": "science", "Technology": "technology", "Humanities": "humanities"}

PREP_GRADES = ("G7", "G8", "G9")


class Command(BaseCommand):
    help = "يقيّد طلاب العام من سجلّ القيد الوزاريّ (xlsx)"

    def add_arguments(self, parser):
        parser.add_argument("path", help="مسار ملفّ سجلّ القيد")
        parser.add_argument("--year", required=True, help="مثال: 2026-2027")
        parser.add_argument("--school", default=None, help="كود المدرسة")
        parser.add_argument(
            "--create-missing",
            action="store_true",
            help="يُنشئ حساباً لمن في السجلّ ولا حسابَ له",
        )
        parser.add_argument(
            "--map",
            nargs="+",
            default=[],
            dest="section_map",
            metavar="شعبةُ‑السجلّ=شعبةُ‑المدرسة",
            help="مطابقةُ ترقيمٍ صريحة، مثل 12/2=12/4",
        )
        parser.add_argument("--apply", action="store_true", help="بدونه يعرض ولا يكتب")

    # ── التنفيذ ──────────────────────────────────────────────────────

    def handle(self, *args, **options):
        school = self._school(options["school"])
        year = options["year"]
        roster, tracks = self._read(options["path"])

        # ترقيمُ السجلّ قد يخالف ترقيم المدرسة — والمطابقةُ تُكتب ولا تُخمَّن.
        mapping = self._mapping(options["section_map"])
        roster = {
            nid: (name, mapping.get(section, section)) for nid, (name, section) in roster.items()
        }

        self.stdout.write(f"\n{school.name} · العام {year}")
        self.stdout.write("═" * 60)
        self.stdout.write(f"  في السجلّ: {len(roster)} طالباً")
        for register_label, school_label in sorted(mapping.items()):
            self.stdout.write(f"  مطابقة: {register_label} في السجلّ ← {school_label} في المدرسة")

        sections = self._plan_sections(school, year, roster, tracks)
        students = self._plan_students(school, year, roster, sections["labels"])

        self._report(sections, students, options)

        if not options["apply"]:
            self.stdout.write("\nعرضٌ فقط. أضف --apply للكتابة.\n")
            return

        if students["unknown"] and not options["create_missing"]:
            raise CommandError(
                f"{len(students['unknown'])} طالباً في السجلّ بلا حساب — أضف "
                "--create-missing لإنشائها، أو أنشئها أوّلاً."
            )

        self._write(school, year, roster, sections, students, options)

    # ── قراءة الملفّ ─────────────────────────────────────────────────

    def _read(self, path):
        """يُعيد سجلّ الطلاب من أوراق الصفوف، ومساراتِ الشُّعب من أسماء أوراقها."""
        try:
            import openpyxl
        except ImportError as exc:  # pragma: no cover - المكتبة في requirements
            raise CommandError("openpyxl غير مثبّتة.") from exc

        try:
            wb = openpyxl.load_workbook(path, data_only=True, read_only=True)
        except FileNotFoundError as exc:
            raise CommandError(f"لا ملفّ في هذا المسار: {path}") from exc

        roster, tracks, seen = {}, {}, Counter()
        for ws in wb.worksheets:
            match = SHEET_TRACK.search(ws.title)
            if match:
                grade, section, track = match.groups()
                tracks[canonical(f"{grade}/{section}")] = TRACKS[track]
            if not ws.title.startswith("الصف-"):
                continue
            for row in ws.iter_rows(min_row=FIRST_DATA_ROW, values_only=True):
                cells = [("" if c is None else str(c).strip()) for c in row[:4]]
                if len(cells) < 4 or not NATIONAL_ID.match(cells[0]):
                    continue
                national_id, name, _grade, section = cells
                seen[national_id] += 1
                roster[national_id] = (name, canonical(section))
        wb.close()

        if not roster:
            raise CommandError("لم يُقرأ طالبٌ واحد — تأكّد أنّه سجلّ القيد.")
        repeated = [k for k, n in seen.items() if n > 1]
        if repeated:
            raise CommandError(f"أرقامٌ مكرّرةٌ في السجلّ: {', '.join(repeated[:5])}")
        return roster, tracks

    # ── الشُّعب ──────────────────────────────────────────────────────

    def _plan_sections(self, school, year, roster, tracks):
        """ما يجب أن يكون من شُعبٍ، وما هو قائمٌ، وأين خالف المسارُ السجلَّ."""
        wanted = sorted({s for _, s in roster.values() if s != NO_SECTION})
        existing = {
            canonical(f"{g.grade[1:]}/{g.section}"): g
            for g in ClassGroup.objects.filter(school=school, academic_year=year)
        }

        missing, wrong_track, labels = [], [], {}
        for label in wanted:
            group = existing.get(label)
            expected = tracks.get(label, "")
            if group is None:
                missing.append((label, expected))
                continue
            labels[label] = group
            if expected and group.track != expected:
                wrong_track.append((label, group.track, expected, group))
        return {
            "wanted": wanted,
            "missing": missing,
            "wrong_track": wrong_track,
            "labels": labels,
            "tracks": tracks,
        }

    # ── الطلاب ───────────────────────────────────────────────────────

    def _plan_students(self, school, year, roster, labels):
        """يقسم السجلّ: من يُقيَّد، ومن لا حسابَ له، ومن لا شعبةَ له."""
        # الطلابُ وحدهم: `absent` تُقارن السجلَّ بمن هم طلابٌ في المنصّة، ولو
        # ضُمّ إليهم الطاقمُ لعُدّ كلُّ معلّمٍ «غائباً عن سجلّ القيد».
        known = {
            u.national_id: u
            for u in CustomUser.objects.filter(
                memberships__school=school,
                memberships__role__name="student",
                memberships__is_active=True,
            ).distinct()
        }
        enrolled = {
            e.student_id: e
            for e in StudentEnrollment.objects.filter(
                is_active=True, class_group__academic_year=year, class_group__school=school
            ).select_related("class_group")
        }

        unknown, unplaced, to_enrol, already, moved, pending = [], [], [], [], [], []
        for national_id, (name, section) in sorted(roster.items()):
            if section == NO_SECTION:
                unplaced.append((national_id, name))
                continue
            user = known.get(national_id)
            if user is None:
                unknown.append((national_id, name, section))
                continue
            group = labels.get(section)
            current = enrolled.get(user.id)
            if group is None:
                # شعبتُه ستُنشأ في هذا التشغيل نفسه. ولولا هذا الدلو لسقط
                # صامتاً — وهو ما كشفه أوّلُ تشغيلٍ جافّ: أربعةُ طلابٍ في
                # شُعب الدعم لم يظهروا في أيّ خانة، ومجموعُ الخانات ٧٠٢ من ٧٠٦.
                pending.append((national_id, name, section))
                continue
            if current is None:
                to_enrol.append((user, group))
            elif current.class_group_id == group.id:
                already.append(national_id)
            else:
                moved.append((user, current, group))

        absent = sorted(set(known) - set(roster))
        return {
            "pending": pending,
            "unknown": unknown,
            "unplaced": unplaced,
            "to_enrol": to_enrol,
            "already": already,
            "moved": moved,
            "absent": absent,
            "known": known,
        }

    # ── العرض ────────────────────────────────────────────────────────

    def _report(self, sections, students, options):
        w = self.stdout.write
        w("\n── الشُّعب ──")
        w(f"  في السجلّ: {len(sections['wanted'])}")
        if sections["missing"]:
            w(self.style.WARNING(f"  تُنشأ ({len(sections['missing'])}):"))
            for label, _track in sections["missing"]:
                w(f"      {label}   (بلا مسار — يُضبط بـ set_class_tracks إن لزم)")
        if sections["wrong_track"]:
            w(
                self.style.WARNING(
                    f"  اسمُ ورقة السجلّ يخالف مسارَ المنصّة في "
                    f"{len(sections['wrong_track'])} شعبة — ولا يُغيَّر شيء:"
                )
            )
            for label, ours, theirs, _ in sections["wrong_track"]:
                w(f"      {label}: المنصّة «{ours or '—'}» · ورقةُ السجلّ «{theirs}»")
            w("      (الحَكَمُ ما يُدرَّس فعلاً — والضبطُ بـ set_class_tracks)")

        w("\n── الطلاب ──")
        w(f"  قيدُهم مطابقٌ أصلاً: {len(students['already'])}")
        w(self.style.SUCCESS(f"  يُقيَّدون في شُعبهم: {len(students['to_enrol'])}"))
        if students["moved"]:
            w(self.style.WARNING(f"  يُنقلون من شعبةٍ إلى أخرى: {len(students['moved'])}"))
            for user, current, group in students["moved"][:10]:
                w(f"      {user.full_name}: {current.class_group} ← {group}")
            if len(students["moved"]) > 10:
                w(f"      … و{len(students['moved']) - 10} غيرهم")
        if students["unknown"]:
            style = self.style.SUCCESS if options["create_missing"] else self.style.ERROR
            verb = "تُنشأ حساباتُهم" if options["create_missing"] else "بلا حساب — لن يُقيَّدوا"
            w(style(f"  {verb}: {len(students['unknown'])}"))
            by_section = Counter(s for _, _, s in students["unknown"])
            for label, count in sorted(by_section.items()):
                w(f"      {label}: {count}")
        if students["pending"]:
            w(self.style.SUCCESS(f"  يُقيَّدون في شُعبٍ تُنشأ الآن: {len(students['pending'])}"))
            for _nid, name, label in students["pending"]:
                w(f"      {label}: {name}")
        if students["unplaced"]:
            w(self.style.WARNING(f"  بلا شعبةٍ في السجلّ — يُتركون: {len(students['unplaced'])}"))
            for national_id, name in students["unplaced"]:
                w(f"      {national_id} — {name}")
        if students["absent"]:
            w(f"  في المنصّة وليسوا في السجلّ — لا يُمسّون: {len(students['absent'])}")

    # ── الكتابة ──────────────────────────────────────────────────────

    @transaction.atomic
    def _write(self, school, year, roster, sections, students, options):
        w = self.stdout.write

        for label, _track in sections["missing"]:
            grade, section = SECTION_LABEL.match(label).groups()
            grade_key = f"G{grade}"
            group = ClassGroup.objects.create(
                school=school,
                grade=grade_key,
                section=section,
                level_type="prep" if grade_key in PREP_GRADES else "sec",
                academic_year=year,
                is_active=True,
            )
            sections["labels"][label] = group
        if sections["missing"]:
            w(self.style.SUCCESS(f"أُنشئت {len(sections['missing'])} شعبة."))

        # الشُّعبُ صارت قائمةً الآن — فيُعاد تخطيطُ الطلاب عليها كي يلحق بها من
        # كانت شعبتُه معلَّقة. والتخطيطُ الأوّل كان للعرض، وهذا للكتابة.
        students = self._plan_students(school, year, roster, sections["labels"])

        created = 0
        if options["create_missing"]:
            from student_affairs.services import StudentService

            for national_id, name, section in students["unknown"]:
                StudentService.create_student(
                    school,
                    {
                        "national_id": national_id,
                        "full_name": name,
                        "class_group_id": sections["labels"][section].id,
                    },
                )
                created += 1
            w(self.style.SUCCESS(f"أُنشئ {created} حساباً وقُيّد أصحابُها."))

        for user, group in students["to_enrol"]:
            StudentEnrollment.objects.create(student=user, class_group=group, is_active=True)
        for user, current, group in students["moved"]:
            current.is_active = False
            current.save(update_fields=["is_active"])
            StudentEnrollment.objects.create(student=user, class_group=group, is_active=True)

        total = len(students["to_enrol"]) + len(students["moved"]) + created
        w(self.style.SUCCESS(f"\nاكتمل القيد: {total} طالباً في العام {year}."))
        if students["unplaced"]:
            w(
                self.style.WARNING(
                    f"وبقي {len(students['unplaced'])} بلا شعبة — قرارُهم لم يُتّخذ في السجلّ."
                )
            )

    # ── مساعدات ──────────────────────────────────────────────────────

    def _mapping(self, pairs):
        """مطابقةُ ترقيمٍ صريحةٌ بين السجلّ والمدرسة: «12/2=12/4».

        لا تُشتقّ من الأعداد ولا من المسار: اشتقاقٌ كهذا يضع سبعةَ طلابٍ في
        جدول شعبةٍ أخرى إن أخطأ، ولا يُخبر أحداً. فمن أراد المطابقة كتبها.
        """
        mapping = {}
        for pair in pairs:
            if pair.count("=") != 1:
                raise CommandError(f"مطابقةٌ بصيغةٍ غير مفهومة: «{pair}» — الصيغة 12/2=12/4")
            register_label, school_label = (canonical(x) for x in pair.split("="))
            if not SECTION_LABEL.match(register_label) or not SECTION_LABEL.match(school_label):
                raise CommandError(f"مطابقةٌ بصيغةٍ غير مفهومة: «{pair}» — الصيغة 12/2=12/4")
            mapping[register_label] = school_label
        collisions = [v for v, n in Counter(mapping.values()).items() if n > 1]
        if collisions:
            raise CommandError(f"شعبتان في السجلّ تُطابقان شعبةً واحدة: {', '.join(collisions)}")
        return mapping

    def _school(self, code):
        if code:
            try:
                return School.objects.get(code=code)
            except School.DoesNotExist as exc:
                raise CommandError(f"لا مدرسة بهذا الكود: {code}") from exc
        schools = list(School.objects.all()[:2])
        if len(schools) != 1:
            raise CommandError("أكثرُ من مدرسة — حدّد --school بالكود.")
        return schools[0]

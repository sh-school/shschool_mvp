"""إغلاقُ القيود المتقادمة — قيدُ عامٍ مضى، ومن لم يعد في سجلّ القيد.

    python manage.py close_stale_enrollments
    python manage.py close_stale_enrollments --not-in-register "سجل_القيد.xlsx"
    python manage.py close_stale_enrollments --register-b64 - < حزمة   # قاعدةٌ لا يصلها الملفّ
    python manage.py close_stale_enrollments … --apply

## العلّة

`is_active` على القيد تقول «هذا السجلُّ المعتمَد»، ولا تقول «هذا سجلُّ هذا
العام». وقيدُ العام الماضي لا يُغلق عند بداية العام: `import_enrolment_register`
يُطفئ القيدَ حين ينتقل الطالبُ **داخل العام نفسِه**، أمّا قيدُ عامٍ مضى فخارجُ
نظره. والقيدُ الفريدُ في القاعدة مفروضٌ على الزوج (طالب، شعبة) — وهما شعبتان في
عامين — فيمرّ.

فحمل مئاتُ الطلاب قيدَين نشطَين معاً. وقد عُولج ما يراه المستخدمُ منه بمُدير
`StudentEnrollment.objects.current_of` (يأخذ أحدثَ القيود عاماً)، لكنّ البيانات
نفسَها بقيت مزدوجة — وهذا الأمرُ ينظّفها.

## وضعان يجتمعان أو يفترقان

**قيدُ عامٍ مضى** (الافتراضيّ): كلُّ قيدٍ نشطٍ لشعبةٍ عامُها ليس العامَ الجاري
يُطفأ. فيعود إلى `is_active` معناها: «قائمٌ الآن» لا «كان قائماً يوماً».

**ومن ليس في سجلّ القيد** (`--not-in-register`): من له قيدٌ نشطٌ في العام الجاري
ولا يذكره السجلُّ الوزاريُّ — خرّيجٌ أو منتقل. وبلا إغلاقه يبقى في كشوف الحضور
والدرجات والتقارير طوالَ العام (قرارُ المستخدم 2026-09-10).

## من يبقى بلا قيدٍ بعد الإغلاق يُسمّى

إغلاقُ قيدِ من لا قيدَ له غيرُه يتركه بلا صفّ — وهذا مقصودٌ لمن غادر المدرسة،
وخطأٌ لمن بقي فيها. فيُعرضون بأسمائهم قبل الكتابة لا بعدها.

ولا يكتب شيئاً بلا `--apply`، وللعمليّة سطرٌ في سجلّ التدقيق.
"""

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from core.models import School
from core.models.academic import StudentEnrollment
from core.models.audit import AuditLog

#: كم اسماً يُعرض من كلّ قائمة — والباقي يُعدّ.
SHOWN = 12


class Command(BaseCommand):
    help = "يُغلق القيودَ المتقادمة: قيدَ عامٍ مضى، ومن لم يعد في سجلّ القيد — بلا كتابةٍ إلّا بـ--apply"

    def add_arguments(self, parser):
        parser.add_argument("--school", default="", help="رمزُ المدرسة — والافتراضُ الأولى")
        parser.add_argument("--year", default="", help="العامُ الجاري — والافتراضُ عامُ المدرسة")
        parser.add_argument(
            "--not-in-register",
            default="",
            metavar="ملفّ",
            help="سجلُّ القيد الوزاريّ — ويُغلق قيدُ من ليس فيه من طلاب العام الجاري",
        )
        # وقاعدةُ الإنتاج لا يصلها ملفُّ الإكسل، فالوضعُ الثاني كان محبوساً عن
        # القاعدة التي تحتاجه أكثرَ من غيرها. والحزمةُ حزمةُ
        # `import_enrolment_register --emit-b64` نفسُها لا صيغةٌ ثانية.
        parser.add_argument(
            "--register-b64",
            default="",
            help=(
                "سجلُّ القيد محزوماً gzip+base64 بدل الملفّ — لقاعدةٍ لا يصلها."
                " و«-» تقرأ الحزمةَ من المدخل القياسيّ، وهو الأسلم"
            ),
        )
        parser.add_argument(
            "--keep-past-years",
            action="store_true",
            help="لا تُغلق قيودَ الأعوام الماضية — لمن أراد الوضعَ الثاني وحدَه",
        )
        parser.add_argument("--apply", action="store_true", help="بدونه يعرض ولا يكتب")

    def handle(self, *args, **options):
        school = self._school(options["school"])
        year = options["year"] or self._year(school)
        if options["not_in_register"] and options["register_b64"]:
            raise CommandError("حدّد --not-in-register أو --register-b64 — لا كليهما.")
        if options["keep_past_years"] and not (
            options["not_in_register"] or options["register_b64"]
        ):
            raise CommandError("--keep-past-years بلا --not-in-register لا يُبقي عملاً.")

        active = StudentEnrollment.objects.filter(is_active=True, class_group__school=school)
        past = (
            StudentEnrollment.objects.none()
            if options["keep_past_years"]
            else active.exclude(class_group__academic_year=year)
        )
        absent = self._absent_from_register(active, year, options)

        self.stdout.write(f"المدرسة: {school.name} · العامُ الجاري {year}")
        self.stdout.write(f"قيودٌ نشطة: {active.count()}")

        doomed = set(past.values_list("id", flat=True)) | set(absent.values_list("id", flat=True))
        if not doomed:
            self.stdout.write(self.style.SUCCESS("لا قيدَ متقادماً — القاعدةُ نظيفة."))
            return

        self._report(past, absent, active, doomed)

        if not options["apply"]:
            self.stdout.write(f"\nعرضٌ فقط — {len(doomed)} قيداً. أضِف --apply للكتابة.")
            return

        closed = self._write(school, year, doomed, options)
        self.stdout.write(self.style.SUCCESS(f"\nأُغلق {closed} قيداً، وللعمليّة سطرٌ في التدقيق."))

    # ── القراءة ──────────────────────────────────────────────────────

    def _absent_from_register(self, active, year, options):
        """قيودُ العام الجاري لمن لا يذكره السجلّ — أو لا شيءَ إن لم يُمرَّر سجلّ."""
        path, packed = options["not_in_register"], options["register_b64"]
        if not path and not packed:
            return StudentEnrollment.objects.none()

        from core.management.commands.import_enrolment_register import (
            Command as RegisterCommand,
        )
        from core.management.commands.import_enrolment_register import _payload, _unpack

        if packed:
            roster, _tracks = _unpack(_payload(packed))
        else:
            roster, _tracks = RegisterCommand()._read(path)
        if not roster:
            raise CommandError("لم يُقرأ طالبٌ واحد من السجلّ.")
        return active.filter(class_group__academic_year=year).exclude(
            student__national_id__in=set(roster)
        )

    def _report(self, past, absent, active, doomed):
        if past.exists():
            years = sorted(set(past.values_list("class_group__academic_year", flat=True)))
            self.stdout.write(f"\n— قيودُ أعوامٍ مضت: {past.count()} ({'، '.join(years)})")
            self._names(past, "يُغلق قيدُهم القديم")
        if absent.exists():
            self.stdout.write(f"\n— في القاعدة وليسوا في السجلّ: {absent.count()}")
            self._names(absent, "يُغلق قيدُهم الجاري")

        # من لا يبقى له قيدٌ نشطٌ واحد — وهو المقصودُ لمن غادر، والخطأُ لمن بقي.
        remaining = active.exclude(id__in=doomed).values_list("student_id", flat=True)
        losing = (
            StudentEnrollment.objects.filter(id__in=doomed)
            .exclude(student_id__in=set(remaining))
            .select_related("student")
        )
        students = {row.student_id: row.student.full_name for row in losing}
        if students:
            self.stdout.write(self.style.WARNING(f"\n— يبقون بلا قيدٍ نشط: {len(students)} طالباً"))
            for name in sorted(students.values())[:SHOWN]:
                self.stdout.write(f"      {name}")
            if len(students) > SHOWN:
                self.stdout.write(f"      … و{len(students) - SHOWN} غيرهم")

    def _names(self, rows, label):
        sample = list(
            rows.select_related("student", "class_group").order_by("student__full_name")[:SHOWN]
        )
        for row in sample:
            self.stdout.write(f"      {row.student.full_name} — {row.class_group}")
        if rows.count() > SHOWN:
            self.stdout.write(f"      … و{rows.count() - SHOWN} غيرهم  [{label}]")

    # ── الكتابة ──────────────────────────────────────────────────────

    @transaction.atomic
    def _write(self, school, year, doomed, options):
        rows = StudentEnrollment.objects.filter(id__in=doomed).select_related("student")
        students = sorted({row.student.full_name for row in rows})
        closed = rows.update(is_active=False)
        AuditLog.objects.create(
            school=school,
            user=None,
            action="update",
            model_name="other",
            object_id="",
            object_repr=f"إغلاقُ {closed} قيداً متقادماً — {year}"[:300],
            # العمليّةُ سطرٌ واحدٌ لا خمسمئة: التدقيقُ يحتاج أن يعرف **ماذا جرى
            # ومتى وبأيّ قاعدة**، والأسماءُ تكفي لتتبّع من فقد قيدَه.
            changes={
                "event": "stale_enrollments_closed",
                "closed": closed,
                "year": year,
                "modes": {
                    "past_years": not options["keep_past_years"],
                    "not_in_register": bool(options["not_in_register"] or options["register_b64"]),
                },
                "students": students,
            },
        )
        return closed

    # ── مساعدات ──────────────────────────────────────────────────────

    def _year(self, school):
        from core.querysets import year_or_current

        return year_or_current(school)

    def _school(self, code):
        school = School.objects.filter(code=code).first() if code else School.objects.first()
        if school is None:
            raise CommandError("لا مدرسةَ بهذا الرمز.")
        return school

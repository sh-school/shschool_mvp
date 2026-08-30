"""
يرفع شريطَي الورق الرسميّ للمدرسة — الترويسة والتذييل.

    python manage.py set_school_letterhead \\
        --head form_header.png --foot form_footer.png --apply

المطبوعات تُصدَّر بترويسة المدرسة وتذييلها كما تعتمدهما، لا بترويسةٍ
مرسومةٍ في القالب: المنصّة متعدّدة المدارس، وصورةٌ مكتوبةٌ في قالبٍ مشترك
تطبع ترويسة مدرسةٍ على وثيقة أخرى.

والملفّان يُخزَّنان في القاعدة كسائر المرفوعات — لا على قرصٍ يزول مع
إعادة النشر.

ولا يكتب شيئاً بلا `--apply`.
"""

import pathlib

from django.core.files import File
from django.core.management.base import BaseCommand, CommandError

from core.models import School

MAX_BYTES = 2 * 1024 * 1024


class Command(BaseCommand):
    help = "يرفع ترويسة المطبوعات وتذييلها لمدرسة"

    def add_arguments(self, parser):
        parser.add_argument("--head", default=None, help="مسار صورة الترويسة")
        parser.add_argument("--foot", default=None, help="مسار صورة التذييل")
        parser.add_argument("--school", default=None, help="كود المدرسة")
        parser.add_argument("--apply", action="store_true", help="بدونه يعرض ولا يكتب")

    def handle(self, *args, **options):
        school = self._school(options["school"])
        jobs = [
            (field, self._image(options[opt]))
            for field, opt in (("letterhead", "head"), ("letterfoot", "foot"))
            if options[opt]
        ]
        if not jobs:
            raise CommandError("لا صورة — مرّر --head أو --foot أو كليهما.")

        self.stdout.write(f"\n{school.name}")
        self.stdout.write("═" * 52)
        for field, path in jobs:
            current = getattr(school, field)
            state = "قائمة، ستُستبدل" if current else "لا شيء"
            label = School._meta.get_field(field).verbose_name
            self.stdout.write(
                f"  {label:18} {state}  ←  {path.name} ({path.stat().st_size // 1024} ك.ب)"
            )

        if not options["apply"]:
            self.stdout.write("\nعرضٌ فقط. أضف --apply للكتابة.\n")
            return

        for field, path in jobs:
            with path.open("rb") as fh:
                getattr(school, field).save(path.name, File(fh), save=False)
        school.save(update_fields=[field for field, _ in jobs])

        self.stdout.write(self.style.SUCCESS(f"\nرُفعت {len(jobs)} صورة."))

    # ── مساعدات ──────────────────────────────────────────────────────

    def _school(self, code):
        school = School.objects.filter(code=code).first() if code else School.objects.first()
        if school is None:
            raise CommandError("لا مدرسة بهذا الكود.")
        return school

    def _image(self, raw):
        """يُرفض ما ليس صورةً أو ما أثقل من الحدّ — قبل أن يدخل القاعدة."""
        path = pathlib.Path(raw)
        if not path.is_file():
            raise CommandError(f"لا ملفّ في هذا المسار: {raw}")
        if path.suffix.lower() not in (".png", ".jpg", ".jpeg"):
            raise CommandError(f"صيغةٌ غير مقبولة: {path.suffix} — المقبول PNG أو JPG.")
        if path.stat().st_size > MAX_BYTES:
            raise CommandError(
                f"الملفّ أثقل من {MAX_BYTES // 1024 // 1024} ميغابايت — " "والصور تُخزَّن في القاعدة."
            )
        return path

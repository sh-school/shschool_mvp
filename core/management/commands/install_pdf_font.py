"""
يُثبّت خطّاً لتوليد وثائق PDF — يحفظه في القاعدة لا في المستودع.

    python manage.py install_pdf_font --file "C:\\Windows\\Fonts\\TRADO.TTF" \\
        --family "Traditional Arabic" --weight 400 --apply

استمارات الوزارة مكتوبةٌ بـ«Traditional Arabic»، وهو ملكيّةُ Monotype
ومستودع هذا المشروع **عامّ** — فإيداعُه فيه نشرٌ لبرمجيّةٍ مرخَّصة.

فيُحفظ في `StoredFile` كسائر المرفوعات (والملفّات في هذه المنصّة تُخزَّن
في القاعدة أصلاً، فلا قرصَ دائم على Railway). ويُخرجه `pdf_utils` إلى
ملفٍّ مؤقّت عند أوّل توليد، فيجده WeasyPrint بمسارٍ مطلق.

وبهذا يصل الخطّ إلى الخادم ولا يدخل الشيفرة المنشورة — والترخيص يبقى
قرار المدرسة، ونطاقُه خادمُها وحده.

ولا يكتب شيئاً بلا `--apply`.
"""

import pathlib

from django.core.management.base import BaseCommand, CommandError

from core.pdf_utils import stored_font_key

MAX_BYTES = 4 * 1024 * 1024


class Command(BaseCommand):
    help = "يُثبّت خطّ PDF في القاعدة (لا في المستودع)"

    def add_arguments(self, parser):
        parser.add_argument("--file", required=True, help="مسار ملفّ الخطّ (.ttf أو .otf)")
        parser.add_argument("--family", required=True, help='اسم العائلة، مثل "Traditional Arabic"')
        parser.add_argument("--weight", default="400", choices=["400", "700"], help="400 أو 700")
        parser.add_argument("--apply", action="store_true", help="بدونه يعرض ولا يكتب")

    def handle(self, *args, **options):
        from core.models.stored_file import StoredFile

        path = self._font(options["file"])
        key = stored_font_key(options["family"], options["weight"])
        existing = StoredFile.objects.filter(name=key).first()

        self.stdout.write(f"\n{options['family']} · وزن {options['weight']}")
        self.stdout.write("═" * 52)
        self.stdout.write(f"  المفتاح   {key}")
        self.stdout.write(
            f"  الحالة    {'قائمٌ، سيُستبدل' if existing else 'لا شيء'}"
            f"  ←  {path.name} ({path.stat().st_size // 1024} ك.ب)"
        )

        if not options["apply"]:
            self.stdout.write("\nعرضٌ فقط. أضف --apply للكتابة.\n")
            return

        payload = path.read_bytes()
        StoredFile.objects.update_or_create(
            name=key,
            defaults={
                "content": payload,
                "size": len(payload),
                "content_type": "font/ttf",
            },
        )
        self.stdout.write(self.style.SUCCESS("\nثُبّت الخطّ في القاعدة."))
        self.stdout.write("ويُخرَج إلى ملفٍّ مؤقّت عند أوّل توليد وثيقة.")

    # ── مساعدات ──────────────────────────────────────────────────────

    def _font(self, raw):
        path = pathlib.Path(raw)
        if not path.is_file():
            raise CommandError(f"لا ملفّ في هذا المسار: {raw}")
        if path.suffix.lower() not in (".ttf", ".otf"):
            raise CommandError(f"صيغةٌ غير مقبولة: {path.suffix} — المقبول TTF أو OTF.")
        if path.stat().st_size > MAX_BYTES:
            raise CommandError(f"الملفّ أثقل من {MAX_BYTES // 1024 // 1024} ميغابايت.")
        return path

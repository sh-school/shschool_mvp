"""حذفُ حصص الجدول المطفأة التي لم يعد لها معنى.

كلُّ توليدٍ كان يُطفئ الجدولَ السابقَ ولا يحذفه، فتراكم في مدرسةٍ واحدةٍ ثمانيةٌ
وعشرون ألفَ صفٍّ مطفأ مقابل ثمانِمئةٍ حيّة — سبعةٌ وتسعون بالمئة من الجدول
نفاياتُ توليداتٍ لم تُعتمد قطّ، تُثقل كلَّ استعلامٍ يمرّ على الجدول.

ما يُحذف: الحصصُ المطفأةُ التي لا مرجعَ توليدٍ لها (ما قبل ربط الحصّة بتوليدها)،
والحصصُ المطفأةُ التي توليدُها مؤرشفٌ أو فاشل.

ما يُبقى: كلُّ حصّةٍ حيّة، وحصصُ المسودّات (فقد تُعتمد غداً)، وحصصُ التوليد المعتمَد.

**والعامُ الجاري وحدَه** — هذا قيدٌ لا خيار. فحارسُ العام يُطفئ جدولَ العام
الماضي عند دخول العام الجديد، والمُطفأُ بلا توليدٍ لا يُميَّز عن نفاياتِ
التوليد بالنظر إلى الصفّ وحده. فلولا هذا القيدُ لابتلع الأمرُ جدولَ العام
الماضي كلَّه في أوّل تشغيلٍ بعد الترفيع — وهو سجلٌّ لا نفاية. و`--all-years`
لمن يعرف ما يفعل.

والافتراضُ عرضٌ لا حذف: `--apply` وحدَها تحذف.
"""

from django.core.management.base import BaseCommand
from django.db.models import Q

from core.academic_calendar import default_academic_year
from operations.models import ScheduleSlot


class Command(BaseCommand):
    help = "يحذف حصص الجدول المطفأة المتراكمة من توليداتٍ لم تُعتمد (عرضٌ افتراضاً، --apply للحذف)"

    def add_arguments(self, parser):
        parser.add_argument("--apply", action="store_true", help="نفّذ الحذف فعلاً")
        parser.add_argument("--year", default=None, help="عامٌ دراسيٌّ بعينه (الجاري افتراضاً)")
        parser.add_argument(
            "--all-years",
            action="store_true",
            help="لا تقصر الحذفَ على عامٍ — يشمل جداولَ الأعوام الماضية",
        )

    def handle(self, *args, **options):
        qs = ScheduleSlot.objects.filter(is_active=False).filter(
            Q(generation__isnull=True) | Q(generation__status__in=("archived", "failed"))
        )

        year = None
        if not options["all_years"]:
            year = options["year"] or default_academic_year()
            qs = qs.filter(academic_year=year)

        total_inactive = ScheduleSlot.objects.filter(is_active=False).count()
        scope = f"العام {year}" if year else "كلّ الأعوام"
        kept = total_inactive - qs.count()
        self.stdout.write(
            f"النطاق: {scope} · مطفأة إجمالاً: {total_inactive} · للحذف: {qs.count()} · "
            f"تُبقى (مسودّات/معتمَد/أعوامٌ أخرى): {kept}"
        )

        if not options["apply"]:
            self.stdout.write(self.style.WARNING("عرضٌ فقط — أضف --apply للحذف."))
            return

        deleted, _ = qs.delete()
        self.stdout.write(self.style.SUCCESS(f"حُذف {deleted} صفّاً."))

"""حذفُ نسخِ الجدول المؤرشفة الزائدة على حدّ الإبقاء.

كلُّ اعتمادٍ يُؤرشف الجدولَ السابق كاملاً ولا يحذفه، فبلغت النسخُ المؤرشفة
خمساً في يومٍ واحد على الإنتاج — أربعةُ آلافٍ وثلاثُمئةٍ وخمسون صفّاً مطفأً
مقابل ثمانِمئةٍ وسبعين حيّة. وقرارُ المدرسة (2026-09-05): **جدولٌ واحدٌ فقط،
الحيّ**.

الاعتمادُ التالي يُنظّف نفسَه من الآن فصاعداً؛ وهذا الأمرُ لتنظيفِ ما تراكم
قبله. حدُّ الإبقاء من الإعداد `SCHEDULE_ARCHIVE_RETENTION` (صفرٌ افتراضاً).

ما لا يُمسّ: التوليدُ المعتمَد، والمسودّاتُ (عملٌ جارٍ قد يُعتمد غداً)، وكلُّ
توليدٍ له حصّةٌ حيّةٌ ولو كانت حالتُه «مؤرشف» — حارسُ `ScheduleGenerationQuerySet`
يرفضه، فلا يفقد الجدولُ الحيُّ نسبَه.

والافتراضُ عرضٌ لا حذف: `--apply` وحدَها تحذف.
"""

from django.conf import settings
from django.core.management.base import BaseCommand

from core.academic_calendar import default_academic_year
from core.models import School
from operations.models import ScheduleGeneration, ScheduleSlot
from operations.services import ScheduleService


class Command(BaseCommand):
    help = "يحذف نسخَ الجدول المؤرشفة الزائدة على حدّ الإبقاء (عرضٌ افتراضاً، --apply للحذف)"

    def add_arguments(self, parser):
        parser.add_argument("--apply", action="store_true", help="نفّذ الحذف فعلاً")
        parser.add_argument("--year", default=None, help="عامٌ دراسيٌّ بعينه (الجاري افتراضاً)")
        parser.add_argument("--school", default=None, help="رمزُ مدرسةٍ بعينها (الكلّ افتراضاً)")
        parser.add_argument(
            "--keep",
            type=int,
            default=None,
            help="كم نسخةً مؤرشفةً تُبقى (الإعداد SCHEDULE_ARCHIVE_RETENTION افتراضاً)",
        )

    def handle(self, *args, **options):
        year = options["year"] or default_academic_year()
        keep = options["keep"]
        if keep is None:
            keep = int(getattr(settings, "SCHEDULE_ARCHIVE_RETENTION", 0))

        schools = School.objects.all()
        if options["school"]:
            schools = schools.filter(code=options["school"])
            if not schools.exists():
                self.stderr.write(self.style.ERROR(f"لا مدرسةَ برمز {options['school']}"))
                return

        total_gens = total_slots = 0
        for school in schools:
            keep_ids = ScheduleService.retained_archived_ids(school, year, keep)
            stale = (
                ScheduleGeneration.objects.filter(
                    school=school, academic_year=year, status="archived"
                )
                .exclude(id__in=keep_ids)
                .exclude(slots__is_active=True)
                .distinct()
            )
            gens = stale.count()
            if not gens:
                continue
            slots = ScheduleSlot.objects.filter(generation__in=stale).count()
            total_gens += gens
            total_slots += slots
            self.stdout.write(
                f"{school.code}: {gens} نسخةً مؤرشفةً و{slots} صفّاً — تُبقى {len(keep_ids)}"
            )

        self.stdout.write(
            f"النطاق: العام {year} · حدُّ الإبقاء: {keep} · "
            f"للحذف: {total_gens} نسخةً و{total_slots} صفّاً"
        )

        if not total_gens:
            self.stdout.write(self.style.SUCCESS("لا شيءَ للحذف."))
            return

        if not options["apply"]:
            self.stdout.write(self.style.WARNING("عرضٌ فقط — أضف --apply للحذف."))
            return

        deleted = sum(
            ScheduleService.retain_archived_generations(school, year, keep) for school in schools
        )
        self.stdout.write(self.style.SUCCESS(f"حُذفت {deleted} نسخةً مؤرشفةً وحصصُها."))

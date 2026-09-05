"""إطفاءُ حصص الجدول الباقية نشطةً من أعوامٍ مضت.

العامُ الدراسيّ يُشتقّ من تقويم الوزارة لا من راية، فيتبدّل بتاريخه بلا أن
يلمس أحدٌ شيئاً — ويبقى جدولُ العام الماضي نشطاً كما تُرك. فتصير في المدرسة
الواحدة نسختان نشطتان، وكلُّ استعلامٍ لا يُقيَّد بالعام يخلطهما.

والقاعدةُ التي يحرسها هذا الأمر واحدة: **لا حصّةَ نشطةٌ خارجَ العام الجاري.**

ويعمل تلقائياً في ثلاثة مواضع — وسيطةُ الطلب اليوميّة، ومرحلةُ الإصدار عند
كلّ نشر، ومهمّةُ Celery إن شُغِّل البيت — فهذا الأمرُ للتشغيل اليدويّ
وللتحقّق. والافتراضُ عرضٌ لا تنفيذ: `--apply` وحدَها تُطفئ.

ولا يحذف شيئاً: الحذفُ قرارُ `prune_schedule_slots` بيد إنسان.
"""

from django.core.management.base import BaseCommand

from core.academic_calendar import academic_year_for_school
from core.models import School
from operations.models import ScheduleSlot
from operations.services import ScheduleService


class Command(BaseCommand):
    help = "يُطفئ حصص الجدول النشطة خارج العام الجاري (عرضٌ افتراضاً، --apply للتنفيذ)"

    def add_arguments(self, parser):
        parser.add_argument("--apply", action="store_true", help="نفّذ الإطفاء فعلاً")
        parser.add_argument("--school", default=None, help="كود مدرسةٍ بعينها (اختياري)")

    def handle(self, *args, **options):
        schools = School.objects.all()
        if options["school"]:
            schools = schools.filter(code=options["school"])
            if not schools.exists():
                self.stderr.write(f"لا مدرسةَ بالكود {options['school']}")
                return

        total = 0
        for school in schools:
            year = academic_year_for_school(school)
            stale = ScheduleSlot.objects.past_years(school).filter(is_active=True)
            count = stale.count()
            total += count

            if count == 0:
                self.stdout.write(f"{school.code} · العام {year} · سليم — لا حصّةَ نشطةً من عامٍ آخر.")
                continue

            years = sorted(set(stale.values_list("academic_year", flat=True)))
            self.stdout.write(
                f"{school.code} · العام {year} · {count} حصّةً نشطةً من: {'، '.join(years)}"
            )

            if options["apply"]:
                ScheduleService.retire_past_year_slots(school)
                self.stdout.write(self.style.SUCCESS(f"  أُطفئت {count} حصّة."))

        if total and not options["apply"]:
            self.stdout.write(self.style.WARNING("\nعرضٌ فقط — أضف --apply للإطفاء."))
        elif not total:
            self.stdout.write(self.style.SUCCESS("\nالقاعدة سليمة."))

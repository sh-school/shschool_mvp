"""إطفاءُ جداول الأعوام الماضية وإسناداتها الباقيةِ نشطة.

العامُ الدراسيّ يُشتقّ من تقويم الوزارة لا من راية، فيتبدّل بتاريخه بلا أن
يلمس أحدٌ شيئاً — ويبقى جدولُ العام الماضي وإسناداتُه نشطةً كما تُركت. فتصير
في المدرسة الواحدة نسختان نشطتان، وكلُّ استعلامٍ لا يُقيَّد بالعام يخلطهما.

والقاعدةُ التي يحرسها هذا الأمر واحدة: **لا سجلَّ نشطٌ خارجَ العام الجاري.**

ويشمل الاثنين معاً — `SubjectClassAssignment` ثمّ `ScheduleSlot` — لأنّ
الإسنادَ أصلُ الجدول: منه يُولَّد، وإسنادُ عامٍ مضى باقٍ نشطاً يُعيد إنتاج
العطب في أوّل توليدٍ بعد الترفيع.

ويعمل تلقائياً في ثلاثة مواضع — وسيطةُ الطلب اليوميّة، ومرحلةُ الإصدار عند
كلّ نشر، ومهمّةُ Celery إن شُغِّل البيت — فهذا الأمرُ للتشغيل اليدويّ
وللتحقّق. والافتراضُ عرضٌ لا تنفيذ: `--apply` وحدَها تُطفئ.

ولا يحذف شيئاً: الحذفُ قرارُ `prune_schedule_slots` بيد إنسان.
"""

from django.core.management.base import BaseCommand

from core.academic_calendar import academic_year_for_school
from core.models import School
from operations.models import ScheduleSlot, SubjectClassAssignment
from operations.services import ScheduleService

#: ما يحرسه الأمر — النموذج واسمُه في التقرير.
GUARDED = (
    (SubjectClassAssignment, "إسناد مادّة"),
    (ScheduleSlot, "حصّة جدول"),
)


class Command(BaseCommand):
    help = "يُطفئ جداول الأعوام الماضية وإسناداتها (عرضٌ افتراضاً، --apply للتنفيذ)"

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
            findings = []

            for model, label in GUARDED:
                stale = model.objects.past_years(school).filter(is_active=True)
                count = stale.count()
                if count:
                    years = sorted(set(stale.values_list("academic_year", flat=True)))
                    findings.append(f"{count} {label} من: {'، '.join(years)}")
                    total += count

            if not findings:
                self.stdout.write(f"{school.code} · العام {year} · سليم.")
                continue

            self.stdout.write(f"{school.code} · العام {year} · " + " · ".join(findings))

            if options["apply"]:
                retired = ScheduleService.retire_past_year_records(school)
                self.stdout.write(
                    self.style.SUCCESS(
                        f"  أُطفئ {retired['assignments']} إسناداً و{retired['slots']} حصّة."
                    )
                )

        if total and not options["apply"]:
            self.stdout.write(self.style.WARNING("\nعرضٌ فقط — أضف --apply للإطفاء."))
        elif not total:
            self.stdout.write(self.style.SUCCESS("\nالقاعدة سليمة."))

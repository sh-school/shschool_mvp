"""فحصُ ربط الجدول الحيّ قبل يوم الدراسة — قراءةٌ فقط (انظر operations/schedule_linkage_audit.py).

    python manage.py audit_schedule_linkage --school <id> [--year 2026-2027] [--date 2026-10-11]

يخرج بالرمز 1 إن وُجد عيبٌ، ليصلح بوّابةً آليّة.
"""

from datetime import date

from django.core.management.base import BaseCommand, CommandError

from core.models import School
from operations import schedule_linkage_audit as audit


class Command(BaseCommand):
    help = "يفحص ربط الجدول الحيّ: إسناد، جرس، تداخل بالساعة، عضويّة، وجلسات يومٍ محدّد"

    def add_arguments(self, parser):
        parser.add_argument("--school", required=True, help="معرّف المدرسة")
        parser.add_argument("--year")
        parser.add_argument("--date", help="YYYY-MM-DD لفحص جلسات اليوم")

    def handle(self, *args, **opts):
        try:
            school = School.objects.get(pk=opts["school"])
        except (School.DoesNotExist, ValueError) as exc:
            raise CommandError("مدرسةٌ غيرُ موجودة.") from exc
        on = date.fromisoformat(opts["date"]) if opts["date"] else None
        year = opts["year"]
        report = audit.audit(school, year, on)
        self.stdout.write(f"العام {report.year} | الحصص الحيّة {report.slots}")
        for f in report.findings:
            self.stdout.write(f"  {'✗' if f.count else '✓'} {f.title}: {f.count}")
            for ref in f.sample:
                self.stdout.write(f"      {ref}")
        if report.sessions_expected is not None:
            self.stdout.write(
                f"  {'✗' if report.sessions_missing else '✓'} جلساتُ {on}: المتوقَّع {report.sessions_expected}"
                f" | الناقص {report.sessions_missing}"
            )
        bare = audit.classes_without_slots(school, report.year)
        if bare:
            self.stdout.write(f"  ✗ شعبٌ بلا حصصٍ: {len(bare)}")
        if not report.ok or bare:
            raise SystemExit(1)

"""يسوّي المعلَّقَ من إدخالات الرصد في أجنحةٍ حُوّلت إلى الرصد النهائيّ (قرارُ المالك 2026-10-07).

`python manage.py settle_direct_entries` (أو `--count`) يعدّ فقط ولا يكتب شيئاً؛ ومعه `--apply` وحدَه يقرّر ما بقي معلَّقاً نهائيّاً بقرارٍ باسم كاتب كلِّ إدخالٍ وأساس `direct_entry`.
لا يمسّ إلا إدخالاتِ الأجنحة التي يشملها المفتاح `ATTENDANCE_GRID_DIRECT_WINGS` (فارغٌ افتراضاً ← لا شيء)، ويعمل مدرسةً مدرسةً بنطاق RLS.
"""

from django.core.management.base import BaseCommand, CommandError

from core.celery_tasks import school_rls_scope
from core.models import School
from operations.attendance_entries import settle_pending_as_direct


class Command(BaseCommand):
    help = "تسويةُ الإدخالات المعلَّقة في أجنحةٍ ذاتِ رصدٍ نهائيّ"

    def add_arguments(self, parser):
        parser.add_argument(
            "--apply", action="store_true", help="يكتب القراراتِ (الافتراضيّ: عدٌّ فقط)"
        )
        parser.add_argument(
            "--count", action="store_true", help="عدٌّ فقط صراحةً (هو الافتراضيّ) — لا يجتمع مع --apply"
        )

    def handle(self, *args, **options):
        if options["apply"] and options["count"]:
            raise CommandError("--count و--apply لا يجتمعان: العدُّ لا يكتب")
        total = 0
        for school in School.objects.filter(is_active=True):
            with school_rls_scope(school.id):
                total += settle_pending_as_direct(school, apply=options["apply"])
        verb = "سُوِّي" if options["apply"] else "سيُسوّى"
        self.stdout.write(f"{verb} {total} إدخالاً معلَّقاً.")

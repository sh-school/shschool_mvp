"""مصالحةُ الجلسات مع الجدول النشط لمدًى من التواريخ.

    python manage.py resync_sessions --from 2026-08-30 --to 2026-09-03 [--dry-run]

لكلّ يوم: تُحذف الجلساتُ التي لا تطابق حصّةً نشطةً (المعلّم، الشعبة، الوقت)
إن كانت `scheduled` وبلا حضور، وتُنشأ الناقصة. ما له حضورٌ يُبقى ويُعَدّ في `kept`.
`--dry-run` يعرض ما سيحدث ولا يكتب شيئاً.
"""

import datetime as dt

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from core.models import School
from operations.services import ScheduleService


class Command(BaseCommand):
    help = "مصالحة الجلسات مع الجدول النشط لمدى تواريخ (حذف غير المطابق بلا حضور + إنشاء الناقص)"

    def add_arguments(self, parser):
        parser.add_argument("--from", dest="start", required=True, help="YYYY-MM-DD")
        parser.add_argument("--to", dest="end", required=True, help="YYYY-MM-DD")
        parser.add_argument("--dry-run", action="store_true", help="عرضٌ بلا كتابة")

    def handle(self, *args, **opts):
        try:
            start, end = dt.date.fromisoformat(opts["start"]), dt.date.fromisoformat(opts["end"])
        except ValueError as e:
            raise CommandError(f"تاريخ غير صالح: {e}") from e
        if end < start:
            raise CommandError("--to قبل --from")

        totals = {"deleted": 0, "created": 0, "kept": 0}
        for school in School.objects.all():
            self.stdout.write(f"== {school.name}")
            d = start
            while d <= end:
                with transaction.atomic():
                    r = ScheduleService.resync_sessions_for_date(school, d)
                    self.stdout.write(
                        f"  {d}: deleted={r['deleted']} created={r['created']} kept={r['kept']}"
                    )
                    for k in totals:
                        totals[k] += r[k]
                    if opts["dry_run"]:
                        transaction.set_rollback(True)
                d += dt.timedelta(days=1)

        tag = "DRY-RUN — لم يُكتب شيء" if opts["dry_run"] else "DONE"
        self.stdout.write(
            self.style.SUCCESS(
                f"{tag}: deleted={totals['deleted']} created={totals['created']} kept={totals['kept']}"
            )
        )

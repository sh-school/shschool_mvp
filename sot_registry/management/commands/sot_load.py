import datetime as dt
import json
from pathlib import Path
from zoneinfo import ZoneInfo

from django.core.management.base import BaseCommand, CommandError

from sot_registry.services import SotError, load_snapshot

DOHA = ZoneInfo("Asia/Qatar")


def in_school_hours(now: dt.datetime) -> bool:
    """الأحد–الخميس 07:00–14:00 بتوقيت الدوحة (نافذةُ الدوام المحميّة)."""
    local = now.astimezone(DOHA)
    return local.weekday() in (6, 0, 1, 2, 3) and dt.time(7, 0) <= local.time() < dt.time(14, 0)


class Command(BaseCommand):
    help = "يحمّل لقطةَ مصدرٍ (JSON خارج git) إلى سجلِّ مصدر الحقيقة: الأحكامُ «غير مدقَّق»، idempotent، بعد الدوام."

    def add_arguments(self, parser):
        parser.add_argument("snapshot", help="مسار ملف اللقطة JSON")
        parser.add_argument(
            "--allow-school-hours",
            action="store_true",
            help="يتجاوز حجبَ نافذة الدوام (بإذن المالك)",
        )

    def handle(self, *args, **options):
        if in_school_hours(dt.datetime.now(dt.UTC)) and not options["allow_school_hours"]:
            raise CommandError(
                "التحميلُ ممنوعٌ في نافذة الدوام (الأحد–الخميس 07:00–14:00 بتوقيت الدوحة)."
            )
        path = Path(options["snapshot"])
        if not path.is_file():
            raise CommandError(f"لا لقطةَ عند {path}: اللقطتان خارج git وتحتاجان وضعًا يدويًّا آمنًا.")
        try:
            result = load_snapshot(json.loads(path.read_text(encoding="utf-8")))
        except SotError as exc:
            raise CommandError(str(exc)) from exc
        self.stdout.write(f"أُنشئ {result['created']} حكمًا وتُخطّي {result['skipped']} موجودًا.")

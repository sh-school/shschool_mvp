"""يسوّي المعلَّقَ من إدخالات الرصد في أجنحةٍ حُوّلت إلى الرصد النهائيّ (قرارُ المالك 2026-10-07، D-271م).

    python manage.py settle_direct_entries                      # عدٌّ فقط (الافتراضيّ) — لا يكتب شيئاً
    python manage.py settle_direct_entries --count --since 2026-10-07
    python manage.py settle_direct_entries --apply --since 2026-10-07 --until 2026-10-08

- **العدُّ الافتراضيّ**: يطبع المؤهَّل والمتعارضَ مع رصدٍ بشريٍّ آخر (يُتخطّى) وما سيُسوّى فعلاً، موزَّعاً بحسب اليوم والجناح. `--apply` وحدَه يكتب.
- **النافذة** `--since/--until`: تاريخُ الحصّة (YYYY-MM-DD، شاملةُ الطرفين).
- **لا إجهاضَ**: الإدخالُ المتعارضُ يُتخطّى ويُسجَّل معرّفُه، وأيُّ خطأٍ آخر يُسجَّل لذلك الإدخال وحدَه ويستمرّ الباقي؛ وسطرُ تدقيقٍ واحدٌ للتشغيل.
- **معرّفاتٌ لا أسماء**: `--ids-out ملف` يكتب معرّفاتِ المتعارض والفاشل (سطراً لكلّ معرّف).
- لا يمسّ إلا أجنحةَ المفتاح `ATTENDANCE_GRID_DIRECT_WINGS` (فارغٌ افتراضاً ← لا شيء)، مدرسةً مدرسةً بنطاق RLS.
"""

import datetime as dt

from django.core.management.base import BaseCommand, CommandError

from core.celery_tasks import school_rls_scope
from core.models import School
from operations.attendance_entries import settle_pending


def _date(raw: str) -> dt.date:
    try:
        return dt.date.fromisoformat(raw)
    except ValueError as exc:
        raise CommandError(f"تاريخٌ غيرُ صالح «{raw}» — الصيغة YYYY-MM-DD") from exc


class Command(BaseCommand):
    help = "تسويةُ الإدخالات المعلَّقة في أجنحةٍ ذاتِ رصدٍ نهائيّ (عدٌّ افتراضاً، و--apply للتطبيق)"

    def add_arguments(self, parser):
        parser.add_argument(
            "--apply", action="store_true", help="يكتب القراراتِ (الافتراضيّ: عدٌّ فقط)"
        )
        parser.add_argument(
            "--count",
            action="store_true",
            help="عدٌّ فقط صراحةً (هو الافتراضيّ) — لا يجتمع مع --apply",
        )
        parser.add_argument("--since", help="أوّلُ تاريخ حصّة (YYYY-MM-DD)")
        parser.add_argument("--until", help="آخرُ تاريخ حصّة (YYYY-MM-DD)")
        parser.add_argument("--ids-out", help="ملفٌّ يُكتب فيه معرّفاتُ المتعارض والفاشل (بلا أسماء)")

    def handle(self, *args, **options):
        if options["apply"] and options["count"]:
            raise CommandError("--count و--apply لا يجتمعان: العدُّ لا يكتب")
        since = _date(options["since"]) if options["since"] else None
        until = _date(options["until"]) if options["until"] else None
        if since and until and since > until:
            raise CommandError("--since بعد --until")

        eligible = settled = 0
        conflicts: list[str] = []
        errors: list[str] = []
        by_day: dict[str, int] = {}
        by_wing: dict[str, int] = {}
        for school in School.objects.filter(is_active=True):
            with school_rls_scope(school.id):
                report = settle_pending(school, apply=options["apply"], since=since, until=until)
            eligible += report.eligible
            settled += report.settled
            conflicts += report.conflicts
            errors += report.errors
            for day, n in report.by_day.items():
                by_day[day] = by_day.get(day, 0) + n
            for wing, n in report.by_wing.items():
                by_wing[wing] = by_wing.get(wing, 0) + n

        window = f"{since or '…'} → {until or '…'}"
        if options["apply"]:
            self.stdout.write(
                f"سُوِّي {settled} إدخالاً (النافذة {window}) | متعارضٌ تُخطّي: {len(conflicts)} | فاشل: {len(errors)}"
            )
        else:
            self.stdout.write(
                f"عدٌّ فقط (النافذة {window}): مؤهَّل {eligible} | متعارضٌ مع رصدٍ بشريٍّ آخر "
                f"(يُتخطّى) {len(conflicts)} | سيُسوّى فعلاً {eligible - len(conflicts)}"
            )
        for label, table in (("بحسب اليوم", by_day), ("بحسب الجناح", by_wing)):
            if table:
                self.stdout.write(
                    f"  {label}: " + "، ".join(f"{k}={v}" for k, v in sorted(table.items()))
                )
        if options["ids_out"] and (conflicts or errors):
            with open(options["ids_out"], "w", encoding="utf-8") as handle:
                handle.writelines(f"conflict {i}\n" for i in conflicts)
                handle.writelines(f"error {i}\n" for i in errors)
            self.stdout.write(f"  المعرّفات (بلا أسماء) في {options['ids_out']}")

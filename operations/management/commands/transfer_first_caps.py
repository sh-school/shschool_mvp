"""ينقل استثناءاتِ سقف الأولى من ملفّ التخفيفات إلى حقل الأدمن (W-20261010-033).

    python manage.py transfer_first_caps --file v2_relaxations_prod.json [--school CODE] [--year Y] [--dry-run]

كانت استثناءاتُ المالك (`first_cap_override`) في ملفٍّ خارج المستودع، فلا تُرى في الأدمن. هذا الأمرُ يكتبها في
`TeacherPreference.max_first_periods` مرّةً واحدة، والمصدرُ بعدها هو الحقل.

- idempotent: تشغيلُه ثانيةً لا يغيّر شيئاً؛ ولا يخفّض قيمةً أعلى كتبها الأدمن.
- لا ينشئ صفَّ تفضيلٍ: الصفُّ الجديد يحمل افتراضاتِ الصفّ (سقفٌ يوميٌّ ٥) فيُغيّر التوليدَ لمن لا صفَّ له.
  فمن لا صفَّ له يُعدّ ويُترك لقرار الإدارة.
- يطبع أعداداً لا أسماء (PDPPL)، ويدوّن في AuditLog قيمتَي قبل/بعد ومعرّفَ الصفّ.
- التنفيذُ على الإنتاج بإذن المالك المباشر وحده.
"""

import json
import uuid
from pathlib import Path
from typing import Any

from django.core.management.base import BaseCommand, CommandError, CommandParser
from django.db import transaction

from core.academic_calendar import academic_year_for_school
from core.models import AuditLog, School
from operations.first_period_cap import MAX_FIRST_PERIODS
from operations.models import TeacherPreference
from operations.models.schedule import MAX_PERSONAL_FIRST


class Command(BaseCommand):
    help = "ينقل first_cap_override من ملف التخفيفات إلى max_first_periods (idempotent، بلا أسماء)"

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("--file", required=True, help="ملفُّ JSON فيه first_cap_override")
        parser.add_argument("--school", default=None)
        parser.add_argument("--year", default="")
        parser.add_argument("--dry-run", action="store_true", help="يعدّ ولا يكتب")

    def handle(self, *args: Any, **opts: Any) -> None:
        school = (
            School.objects.filter(code=opts["school"]).first()
            if opts["school"]
            else School.objects.first()
        )
        if school is None:
            raise CommandError("لا مدرسة")
        year = opts["year"] or academic_year_for_school(school)
        try:
            spec = json.loads(Path(opts["file"]).read_text(encoding="utf-8"))
            overrides = {
                str(t): int(c) for t, c in dict(spec.get("first_cap_override") or {}).items()
            }
        except (OSError, ValueError, TypeError, AttributeError) as error:
            raise CommandError(f"ملفٌّ غيرُ صالح: {type(error).__name__}") from error

        counts = {"updated": 0, "unchanged": 0, "no_row": 0, "out_of_range": 0}
        with transaction.atomic():
            for teacher_id, cap in sorted(overrides.items()):
                if not MAX_FIRST_PERIODS < cap <= MAX_PERSONAL_FIRST:
                    counts["out_of_range"] += 1
                    continue
                try:
                    teacher_uuid = uuid.UUID(teacher_id)
                except ValueError:  # معرّفٌ ليس UUID (ملفٌّ بأسماء مموَّهة): يُعدّ بلا صفّ لا يُسقط الأمر
                    counts["no_row"] += 1
                    continue
                pref = TeacherPreference.objects.filter(
                    school=school, academic_year=year, teacher_id=teacher_uuid
                ).first()
                if pref is None:
                    counts["no_row"] += 1
                    continue
                if pref.max_first_periods is not None and pref.max_first_periods >= cap:
                    counts["unchanged"] += 1
                    continue
                counts["updated"] += 1
                if opts["dry_run"]:
                    continue
                before, pref.max_first_periods = pref.max_first_periods, cap
                pref.save(update_fields=["max_first_periods"])
                AuditLog.objects.create(
                    school=school,
                    user=None,
                    action="update",
                    model_name="other",
                    object_id=str(pref.pk),
                    object_repr=f"سقفُ الأولى الشخصيّ {year}",
                    changes={
                        "event": "teacher_first_period_cap_changed",
                        "channel": "transfer_command",
                        "before": before,
                        "after": cap,
                    },
                )
        mode = "عدٌّ فقط (dry-run)" if opts["dry_run"] else "كُتب"
        self.stdout.write(
            f"{mode}: محدَّث={counts['updated']} بلا تغيير={counts['unchanged']} "
            f"بلا صفّ تفضيل={counts['no_row']} خارج المدى={counts['out_of_range']} "
            f"من أصل {len(overrides)}"
        )

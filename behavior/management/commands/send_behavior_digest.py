"""إرسالُ ملخّص مخالفات الرصد يدويّاً — لتدارك يومٍ غابت فيه خدمةُ Beat.

    python manage.py send_behavior_digest                     # آخرُ خمسة أيّامٍ دراسيّة
    python manage.py send_behavior_digest --date 2026-09-13   # يومٌ بعينه
    python manage.py send_behavior_digest --school <uuid>     # مدرسةٌ واحدة

آمنٌ للتكرار: ما أُرسل لا يُعاد (`behavior/digest.py`).
"""

from __future__ import annotations

import datetime as dt
import uuid
from typing import Any

from django.core.management.base import BaseCommand, CommandError, CommandParser
from django.utils import timezone

from behavior.digest import school_days_back, send_for_schools


class Command(BaseCommand):
    help = "يرسل ملخّصَ مخالفات الرصد لأولياء الأمور — ولا يُعيد ما أُرسل."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("--date", help="يومُ الحصص YYYY-MM-DD (افتراضاً: آخرُ خمسة أيّام)")
        parser.add_argument("--school", help="معرّفُ مدرسةٍ واحدة (افتراضاً: كلُّ النشطة)")

    def handle(self, *args: Any, **options: Any) -> None:
        today = timezone.localdate()
        if options["date"]:
            try:
                days = [dt.date.fromisoformat(options["date"])]
            except ValueError as exc:
                raise CommandError("التاريخ بصيغة YYYY-MM-DD") from exc
        else:
            days = school_days_back(today)
        school_id = None
        if options["school"]:
            # يُفحص هنا: معرّفٌ مشوَّهٌ يُسقطه `UUIDField` بـ`ValidationError` خارجَ
            # احتواء المدرسة، فيخرج أثراً خاماً بدل رسالة.
            try:
                school_id = str(uuid.UUID(options["school"]))
            except ValueError as exc:
                raise CommandError("معرّف المدرسة UUID") from exc
        result = send_for_schools(days, today=today, school_id=school_id)
        self.stdout.write(f"أُرسل {result['sent']} ملخّصاً، وتعثّرت {result['failed_schools']} مدرسة.")

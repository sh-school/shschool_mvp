"""استيرادُ لقطة خارطة التجويد إلى القاعدة.

    python manage.py import_roadmap_snapshot <path-to-json>

اللقطةُ ملفٌّ JSON بمفاتيح items وkpis وdecisions وrisks وchecklist وmeta. **لا تُودَع في
المستودع** (عامّ، وفي الخارطة تفاصيلُ أمنيّةٌ حسّاسة): يُمرَّر مسارُها وسيطاً. والأمرُ
idempotent: `update_or_create` بالرمز، فتشغيلُه ثانيةً لا يُضاعف صفّاً — لكنّه **يعيد كتابةَ
كلّ حقلٍ في اللقطة**، فما عُدِّل من الواجهة (الحالة والتقدّم والتواريخ) يرجع إلى ما في الملفّ.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from django.core.management.base import BaseCommand, CommandError, CommandParser

from roadmap.import_services import import_snapshot
from roadmap.services import RoadmapError


class Command(BaseCommand):
    help = "يستورد لقطةَ خارطة التجويد (JSON) — idempotent بالرمز، ويُبلِغ بالمُنشأ والمُحدَّث"

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("path", help="مسارُ ملفّ اللقطة (JSON)")

    def handle(self, *args: Any, path: str, **options: Any) -> None:
        source = Path(path)
        if not source.is_file():
            raise CommandError(f"لا ملفَّ في {source}")
        try:
            data = json.loads(source.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise CommandError(f"تعذّرت قراءةُ اللقطة: {exc}") from exc
        try:
            report = import_snapshot(data)
        except RoadmapError as exc:
            detail = "\n".join(f"  - {key}: {value}" for key, value in exc.errors.items())
            raise CommandError(f"لقطةٌ مرفوضة (لم يُكتب شيء):\n{detail}") from exc
        for line in report.lines():
            self.stdout.write(line)
        self.stdout.write(self.style.SUCCESS("تمّ الاستيراد"))

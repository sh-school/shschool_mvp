"""بذرُ مدرسة اختبار الحمل (W-20261027-036) — خادمُ الجلسة المحلّيّ وحدَه.

    LOADTEST_ACCOUNTS_PASSWORD=... python manage.py seed_loadtest --students 1000 --accounts 20

الإنتاجُ وقاعدةُ المعاينة مرفوضان. الكلمةُ من البيئة لا من وسيط. التوثيقُ: tests/loadtest/README.md.
"""

from __future__ import annotations

import os
from typing import Any

from django.core.management.base import BaseCommand, CommandError, CommandParser

from core import loadtest_seed as service

PASSWORD_ENV = "LOADTEST_ACCOUNTS_PASSWORD"  # pragma: allowlist secret — اسمُ متغيّر البيئة لا قيمتُه


class Command(BaseCommand):
    help = "بذرُ طلبةٍ بحجمٍ وحساباتِ موظّفين متعدّدة لاختبار الحمل (محلّيّ وحدَه)"

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("--students", type=int, default=service.DEFAULT_STUDENTS)
        parser.add_argument("--accounts", type=int, default=service.DEFAULT_ACCOUNTS)

    def handle(self, *args: Any, **options: Any) -> None:
        problems = service.environment_problems()
        if problems:
            raise CommandError("رُفض بذرُ مدرسة الحمل — " + "؛ ".join(problems))
        password = os.environ.get(PASSWORD_ENV, "")
        if not password:
            raise CommandError(f"رُفض: لا كلمةَ مرور — عيّن {PASSWORD_ENV}")
        try:
            result = service.seed(password, options["students"], options["accounts"])
        except ValueError as exc:
            raise CommandError(str(exc)) from exc
        self.stdout.write(
            f"مدرسةُ الحمل: طلبة جدد {result.students}؛ شُعب جديدة {result.classes}؛ "
            f"حسابات جديدة {result.accounts}."
        )

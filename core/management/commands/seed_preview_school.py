"""بذرُ المدرسة الوهميّة الثانية على 8500 (W-20261004-006) — لا يعمل إلّا في المعاينة.

    python manage.py seed_preview_school           # يبذر (متساوي الأثر)
    python manage.py seed_preview_school --check   # يفشل إن وُجدت المدرسةُ خارج المعاينة

الحارسُ نفسُه لحسابات المدرسة الأولى: `environment_problems()` + ربطٌ على loopback + كلمةٌ من البيئة.
"""

from __future__ import annotations

import os
from typing import Any

from django.core.management.base import BaseCommand, CommandError, CommandParser

from core import preview_school_seed as service
from core.management.commands.preview_accounts import bind_is_loopback, environment_problems
from core.preview_school import preview_school_in_wrong_environment

PASSWORD_ENV = "PREVIEW_ACCOUNTS_PASSWORD"  # pragma: allowlist secret — اسمُ متغيّر البيئة لا قيمتُه


class Command(BaseCommand):
    help = "بذرُ مدرسة المعاينة الثانية (اثنا عشر دوراً) — المعاينةُ وحدَها"

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("--check", action="store_true")

    def handle(self, *args: Any, **options: Any) -> None:
        if options["check"]:
            if preview_school_in_wrong_environment():
                raise CommandError("مدرسةُ المعاينة الثانيةُ موجودةٌ خارج بيئة المعاينة")
            self.stdout.write("لا أثرَ لمدرسة المعاينة الثانية خارج المعاينة.")
            return
        problems = environment_problems()
        if problems:
            raise CommandError("رُفض بذرُ مدرسة المعاينة الثانية — " + "؛ ".join(problems))
        if not bind_is_loopback():
            raise CommandError("رُفض: PREVIEW_BIND ليس loopback")
        password = os.environ.get(PASSWORD_ENV, "")
        if not password:
            raise CommandError(f"رُفض: لا كلمةَ مرور — عيّن {PASSWORD_ENV}")
        try:
            result = service.seed(password)
        except ValueError as exc:
            raise CommandError(str(exc)) from exc
        self.stdout.write(
            f"مدرسةُ المعاينة الثانية: حسابات أُنشئ {result.accounts_created} وصُحّح {result.accounts_fixed}؛ "
            f"شُعب جديدة {result.classes}؛ طلبة جدد {result.students}."
        )

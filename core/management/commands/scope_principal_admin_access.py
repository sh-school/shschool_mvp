"""يستبدل `is_superuser` عن حساب المدير بـ`is_staff` وصلاحيّاتٍ صريحة.

    python manage.py scope_principal_admin_access --apply

قرارُ المالك (2026-09-22): «ليس كلُّ شيءٍ متاحاً للمدير في صفحات الإدارة».
وكان `full_seed.py` يمنحه `is_superuser` مباشرةً — يتجاوز نظامَ الصلاحيّات
بالكامل بلا استثناء، فلا حارسَ تعدّى `AuditLog` المحمي من الحذف صراحةً.

هذا الأمرُ **لحسابات الإنتاج القائمة** التي مُنحت `is_superuser` بالطريقة
القديمة؛ `full_seed.py` نفسُه صار يمنح الصلاحيّةَ الجديدةَ من الآن. ولا يُمسّ
حسابُ مطوّرِ المنصّة ولا أيُّ `superuser` آخرَ سبَبُه غيرُ الدور `principal`
(`core.developer_access` يتحقّق من المجموعة أو `superuser` بمعزلٍ عن هذا).

ولا يكتب شيئاً بلا `--apply`.
"""

from __future__ import annotations

from argparse import ArgumentParser
from typing import Any

from django.core.management.base import BaseCommand
from django.db import transaction

from core.admin_access import sync_principal_admin_group
from core.models import CustomUser
from core.models.access import Membership


class Command(BaseCommand):
    help = "يستبدل is_superuser عن حساب المدير بـis_staff وصلاحيّاتٍ صريحة (core.admin_access)"

    def add_arguments(self, parser: ArgumentParser) -> None:
        parser.add_argument("--apply", action="store_true", help="بدونه يعرض ولا يكتب")

    def handle(self, *args: Any, **options: Any) -> None:
        principal_ids = set(
            Membership.objects.filter(is_active=True, role__name="principal").values_list(
                "user_id", flat=True
            )
        )
        targets = list(
            CustomUser.objects.filter(id__in=principal_ids, is_superuser=True).order_by("full_name")
        )

        self.stdout.write(f"\nحساباتُ مديرٍ بـis_superuser: {len(targets)}")
        self.stdout.write("═" * 52)
        for user in targets:
            self.stdout.write(f"  · {user.full_name}")

        if not options["apply"]:
            self.stdout.write("\nعرضٌ فقط. أضف --apply للكتابة.\n")
            return

        with transaction.atomic():
            group = sync_principal_admin_group()
            for user in targets:
                user.is_superuser = False
                user.is_staff = True
                user.save(update_fields=["is_superuser", "is_staff"])
                user.groups.add(group)

        self.stdout.write(
            self.style.SUCCESS(f"\nحُوِّل {len(targets)} حساباً إلى is_staff بصلاحيّاتٍ صريحة.")
        )

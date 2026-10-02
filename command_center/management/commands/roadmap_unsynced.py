"""طابورُ مزامنة الخارطة: الطلباتُ المدموجةُ التي لم يُذكر رقمُها في أيِّ بندٍ (MAE-11) — قراءةٌ فقط، لا يكتب شيئاً.

    python manage.py roadmap_unsynced

يقرأ GitHub العامّ بالجلب الشرطيّ نفسِه الذي تستعمله لوحةُ «مزامنةُ الخارطة»، ويطبع رقمَ كلّ طلبٍ وعمرَ دمجه بالساعات.
تقرؤه «0701 · تحديث الخارطة» (أو أيُّ مطوّر) لتعرف ما بقي. والأرقامُ هنا لا في اللوحة (لا رقمَ طلبٍ في `contract.py`).
"""

from __future__ import annotations

import time
from typing import Any

from django.core.management.base import BaseCommand

from command_center.collectors import github, sync


class Command(BaseCommand):
    help = "الطلباتُ المدموجةُ التي لم تُذكر في الخارطة (قراءةٌ فقط)"

    def now(self) -> float:
        return time.time()

    def handle(self, *args: Any, **options: Any) -> None:
        merged = github.fetch(sync.MERGED_PATH, sync.reduce_merged)
        if merged is None:
            self.stderr.write("تعذّرت قراءةُ GitHub (شبكةٌ أو حدُّ الطلبات)")
            return
        raw = merged.get("prs")
        prs: list[list[float]] = raw if isinstance(raw, list) else []
        missing = sync.unsynced(prs, sync.synced_numbers())
        moment = self.now()
        if not missing:
            self.stdout.write("كلُّ المدموج مذكورٌ في الخارطة.")
            return
        self.stdout.write(f"{len(missing)} طلباً دُمج ولم يُذكر في الخارطة (من آخر {len(prs)}):")
        for number, merged_at in missing:
            hours = (moment - merged_at) / 3600
            mark = "متأخّر" if hours > sync.GRACE_HOURS else "ضمن المهلة"
            self.stdout.write(f"  #{number} — قبل {hours:.0f} س ({mark})")

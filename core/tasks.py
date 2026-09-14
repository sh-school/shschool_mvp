"""مهامُّ Celery العامّة للمنصّة — ما ليس لوحدةٍ بعينها.

* `core.enforce_data_retention` — إنفاذُ سياسة الاحتفاظ بالبيانات
  (`core/retention.py`)، تُجدوَل أسبوعيّاً فجراً في `shschool/celery.py`.
"""

from __future__ import annotations

from typing import Any

from celery import shared_task

from core.retention import enforce_retention


@shared_task(name="core.enforce_data_retention")
def enforce_data_retention(dry_run: bool = False) -> dict[str, Any]:
    """يحذف ما انقضت مدّتُه وفق `PDPPL_DATA_RETENTION_DAYS`، ويُعيد الأعداد.

    ثابتةُ التكرار وبدفعات؛ والصفرُ في الإعداد يعطّلها فتعود بلا حذف. والملخّصُ
    يُكتب في `AuditLog(action="delete")` داخل الخدمة نفسها — لا هنا — كي يشترك
    فيه أمرُ `manage.py enforce_retention`.
    """
    return enforce_retention(dry_run=dry_run).as_changes()

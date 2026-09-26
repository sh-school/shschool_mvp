"""مهمّتا الجمع الآليّ لـ«مركز قيادة الجودة» — تُجدوَلان في `shschool/celery.py`، وتُطلقهما `refresh.ensure_fresh` عند غياب Beat.

`command_center.collect_local` كلَّ دقيقة (قاعدةٌ وcache وملفّات)، و`command_center.collect_remote` كلَّ أربع دقائق (GitHub بطلباتٍ شرطيّة).
كلٌّ منهما يعزل عطلَ كلّ مجمِّعٍ عن الباقين (`collectors.run`). والعاملُ لا يُعيد تحميلَ الكود: تعديلُ مجمِّعٍ يلزمه إعادةُ تشغيله.
"""

from __future__ import annotations

from celery import shared_task

from command_center import collectors


@shared_task(
    name="command_center.collect_local", ignore_result=True, soft_time_limit=60, time_limit=90
)
def collect_local() -> dict[str, bool]:
    return collectors.run(collectors.LOCAL)


@shared_task(
    name="command_center.collect_remote", ignore_result=True, soft_time_limit=60, time_limit=90
)
def collect_remote() -> dict[str, bool]:
    return collectors.run(collectors.REMOTE)

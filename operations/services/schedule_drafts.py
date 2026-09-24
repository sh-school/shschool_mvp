"""schedule_drafts.py — حذفُ توليدٍ لم يُعتمد: مسودّةٌ أو محاولةٌ فاشلة.

كان حذفُ المسودّة لا يكون إلّا من لوحة الإدارة الخلفيّة: يولّد النائبُ جدولاً
ويراه ولا يرضاه، فيبقى صفُّه في القائمة وحصصُه المطفأةُ في القاعدة حتى يدخل
أحدٌ الخلفيّةَ ويحذفه بيده — وحذفُه هناك أثناء التشغيل أسقط توليداً جارياً في
2026-09-24 («Save with update_fields did not affect any rows»).

فالحذفُ هنا بشرطين لا يُتنازل عنهما:
- **ما لم يُعتمد وحدَه** (`draft`، `failed`): المعتمَدُ جدولُ المدرسة الحيّ،
  والمؤرشَفُ نسخةُ التراجع — ولا يُحذفان من هذا الباب.
- **ولا ما يجري الآن** (`queued`، `running`): العاملُ ما زال يكتب في صفّه، وحذفُه
  تحت يده هو العطبُ نفسُه. والمعلّقُ بلا عاملٍ يُنهيه `_reap_stale_generations`
  فاشلاً بعد عشرين دقيقة، ثمّ يُحذف من هنا.

وحصصُ المسودّة مطفأةٌ بطبعها (`is_active=False`)؛ فإن وُجدت منها حصّةٌ حيّةٌ رُفض
الحذفُ كلُّه — فذلك جدولٌ نُشر بطريقٍ قديمٍ لا مسودّة. والحذفُ يُسجَّل في سجلّ
التدقيق بصاحبه وعدد حصصه قبل أن يزول الصفّ.
"""

from __future__ import annotations

from django.db import transaction
from django.utils import timezone

from core.models.audit import AuditLog
from operations.models import ScheduleGeneration, ScheduleSlot

#: ما يجوز حذفُه: ما لم يُعتمد ولا يجري.
DISCARDABLE = ("draft", "failed")


class DiscardRefusedError(Exception):
    """توليدٌ لا يُحذف من هذا الباب — والسببُ يُقال للمستخدم كما هو."""


def can_discard(generation: ScheduleGeneration) -> bool:
    return generation.status in DISCARDABLE


@transaction.atomic
def discard_generation(generation: ScheduleGeneration, *, user, request=None) -> int:
    """يحذف توليداً لم يُعتمد مع حصصه المطفأة، ويعيد عددَ الحصص المحذوفة."""
    locked = ScheduleGeneration.objects.select_for_update().get(pk=generation.pk)
    if locked.status in ScheduleGeneration.PENDING_STATUSES:
        raise DiscardRefusedError("هذا التوليدُ ما زال يجري — انتظر انتهاءَه ثمّ احذفه.")
    if not can_discard(locked):
        raise DiscardRefusedError("لا يُحذف إلّا جدولٌ لم يُعتمد — المعتمَدُ والمؤرشَفُ باقيان.")
    slots = ScheduleSlot.objects.filter(generation=locked)
    if slots.filter(is_active=True).exists():
        raise DiscardRefusedError("لهذا التوليد حصصٌ في الجدول الحيّ — لا يُحذف من هنا.")

    removed, _ = slots.delete()
    AuditLog.log(
        user=user,
        action="delete",
        model_name="other",
        object_id=locked.pk,
        object_repr=f"توليدُ جدول {locked.academic_year} ({locked.get_status_display()})",
        changes={
            "status": locked.status,
            "generated_at": locked.generated_at.isoformat() if locked.generated_at else None,
            "slots": removed,
        },
        school=locked.school,
        request=request,
    )
    locked.delete()
    return removed


def is_stopped(generation_id) -> bool:
    """أيجب أن يقف التوليدُ الآن؟ — الصفُّ لم يعد «يجري»: أُوقف أو حُذف."""
    return not ScheduleGeneration.objects.filter(pk=generation_id, status="running").exists()


@transaction.atomic
def stop_generation(generation: ScheduleGeneration, *, user, request=None) -> None:
    """يوقف توليداً في الانتظار أو جارياً: يصير «فشل» بسببٍ مكتوب، فيظهر زرُّ حذفه.

    والعاملُ يرى ذلك عند أقرب حدٍّ آمن (بين المحاولات، وقبل السداد، وتحت قفل
    الصفّ قبل الحفظ) فيقف ولا يكتب شيئاً. وما في الانتظار لا يبدأ أصلاً.
    """
    from operations.scheduler import GENERATION_STOPPED

    locked = ScheduleGeneration.objects.select_for_update().get(pk=generation.pk)
    if locked.status not in ScheduleGeneration.PENDING_STATUSES:
        raise DiscardRefusedError("لا توليدَ جارياً ليُوقف — انتهى أو أُوقف قبلُ.")
    was = locked.status
    locked.status = "failed"
    locked.error_message = GENERATION_STOPPED
    locked.finished_at = timezone.now()
    locked.save(update_fields=["status", "error_message", "finished_at"])
    AuditLog.log(
        user=user,
        action="update",
        model_name="other",
        object_id=locked.pk,
        object_repr=f"إيقافُ توليد جدول {locked.academic_year}",
        changes={"status": [was, "failed"], "stopped": True},
        school=locked.school,
        request=request,
    )

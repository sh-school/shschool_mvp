"""operations/services/schedule.py — واجهةُ الجدول الأسبوعيّ والجلسات المشتقّة منه.

`ScheduleService` تجمع ثلاثة مقاطع (البند 8، الخطوة 2): القراءة والأرشفة والجلسات؛
وتحتفظ بما يمسّ أكثر من مقطع (`approve_generation`) وبـ`create_exemption`.
الاستدعاء `ScheduleService.x(...)` وباتشاتُ الاختبار عليه كما كانا.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from django.db import transaction

from operations.models import (
    ScheduleGeneration,
    ScheduleSlot,
    TeacherExemption,
)

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from core.models import CustomUser, School

from operations.services.schedule_read import ScheduleReadMixin, parallel_labels
from operations.services.schedule_retention import ScheduleRetentionMixin
from operations.services.schedule_sessions import ScheduleSessionsMixin

__all__ = ["ScheduleService", "parallel_labels"]


class ScheduleService(ScheduleReadMixin, ScheduleRetentionMixin, ScheduleSessionsMixin):
    @classmethod
    def approve_generation(
        cls, gen: ScheduleGeneration, *, notify: bool = True, acknowledged: bool = False
    ) -> dict:
        """الاعتمادُ هو النشر — فعلٌ واحدٌ يستوي فيه زرُّ الشاشة وأمرُ النقل.

        حصصُ هذه المسودّة تُفعَّل ويُطفأ ما سواها في العام نفسِه. وكان الاعتمادُ
        يقلب حقلَ حالةٍ لا غير، والحصصُ حيّةٌ منذ لحظة التوليد — فلم يكن الزرُّ
        يقرّر شيئاً. والمسودّاتُ الأقدمُ من حقل التوليد حصصُها حيّةٌ أصلاً وبلا
        مرجع، فإطفاءُ الحيّ لها يمحو الجدولَ كلَّه: تُعامَل كما كانت — قلبَ حالةٍ.

        والاعتمادُ والإشعارُ فعلٌ واحدٌ في معاملةٍ واحدة: كان الحفظُ يسبق
        `bulk_create` بلا معاملة، فحين سقط الإدراجُ بقي الجدولُ «معتمَداً» ولم
        يعلم به معلّمٌ واحد. و`school` على صفّ الإشعار لازمٌ لا زينة — صفٌّ
        مستأجِرٌ تحرسه RLS، وبلا مدرسةٍ ترفضه السياسةُ fail-closed فتسقط العمليّة.

        ثمّ تُصالَح جلساتُ الأسبوع الجاري: تحمل الجدولَ القديم، والتوليدُ لا يعيد
        يوماً فيه جلسات — فيُحذف ما لا يطابق ولا حضورَ عليه، ويُنشأ الناقص.

        يُعيد `{"notified": n, "sync": {"deleted", "created", "kept"}}`.
        """
        from core.academic_calendar import academic_year_for_school
        from core.models import Membership
        from notifications.models import InAppNotification

        from ..schedule_breaches import BreachesNotAcknowledgedError, approval_refusal

        # مخالفةٌ صلبةٌ في المسودّة لا تُعتمد إلّا بإقرارٍ صريحٍ (SCH-05) — هنا لا في العرض:
        # فأمرُ النقل والاستيرادُ يمرّان من هذا الباب أيضاً، ولا يُتجاوز الحارسُ بطريقٍ آخر.
        refusal = approval_refusal(gen, acknowledged)
        if refusal:
            raise BreachesNotAcknowledgedError(refusal)

        school = gen.school
        with transaction.atomic():
            draft_slots = ScheduleSlot.objects.filter(generation=gen)
            if draft_slots.exists():
                ScheduleSlot.objects.filter(
                    school=school, academic_year=gen.academic_year, is_active=True
                ).exclude(generation=gen).update(is_active=False)
                draft_slots.update(is_active=True)

            ScheduleGeneration.objects.filter(
                school=school, academic_year=gen.academic_year, status="approved"
            ).update(status="archived")
            # والمؤرشَفُ الزائدُ على حدّ الإبقاء (نسختان افتراضاً، SCH-07) يذهب مع حصصه.
            cls.retain_archived_generations(school, gen.academic_year)

            gen.status = "approved"
            # ويُعاد القياسُ عند الاعتماد: المصادقةُ قد تكون بعد تعديلٍ يدويّ على المسودّة.
            try:
                from operations.schedule_lab import store_metrics

                store_metrics(gen)
            except Exception:  # noqa: BLE001
                logger.exception("schedule_lab: تعذّر القياسُ عند الاعتماد %s", gen.id)
            gen.save(update_fields=["status"])

            notified = 0
            if notify:
                teacher_ids = Membership.objects.filter(
                    school=school,
                    is_active=True,
                    role__name__in=(
                        "teacher",
                        "coordinator",
                        "ese_teacher",
                        "activities_coordinator",
                        "e_projects_coordinator",
                    ),
                ).values_list("user_id", flat=True)
                notifs = [
                    InAppNotification(
                        user_id=tid,
                        school=school,
                        title="تم اعتماد الجدول الدراسي",
                        body=(
                            f"تم اعتماد الجدول للعام {gen.academic_year}. "
                            "راجع جدولك من صفحة الجدول الأسبوعي."
                        ),
                        event_type="general",
                        priority="medium",
                        related_url="/teacher/weekly-schedule/",
                    )
                    for tid in teacher_ids
                ]
                InAppNotification.objects.bulk_create(notifs)
                notified = len(notifs)

        sync = {"deleted": 0, "created": 0, "kept": 0}
        queued = False
        if gen.academic_year == academic_year_for_school(school):
            sync = cls.resync_current_week(school, gen.academic_year)
            queued = cls._queue_future_weeks_resync(school, gen.academic_year)
        return {"notified": notified, "sync": sync, "future_weeks_queued": queued}

    @staticmethod
    def _queue_future_weeks_resync(school: School, academic_year: str) -> bool:
        """الأسابيعُ المولَّدةُ بعد الجاري تُصالَح في الخلفيّة — وعطبُ الوسيط لا يُسقط اعتماداً.

        فالاعتمادُ تمّ والمعلّمون أُشعروا، وما فاته مصالحةُ أسابيعَ قادمةٍ يُعاد بها الأمرُ
        نفسُه (`sync_schedule` أو المهمّةُ ذاتُها). فيُسجَّل العطبُ ويُقال، ولا يُخفى.
        """
        from operations.tasks import resync_generated_sessions_task

        def send() -> None:
            try:
                resync_generated_sessions_task.delay(str(school.pk), academic_year)
            except Exception:  # noqa: BLE001 — يُسجَّل ولا يُبتلع
                logger.exception("تعذّر إرسال مصالحة الأسابيع المولَّدة للمدرسة %s", school.pk)

        transaction.on_commit(send)
        return True

    @staticmethod
    @transaction.atomic
    def create_exemption(
        school: School,
        teacher: CustomUser,
        academic_year: str,
        exemption_type: str,
        day_of_week: int,
        period_number,
        reason: str = "",
        created_by: CustomUser | None = None,
        source: str = "school",
    ):
        """
        إضافة تفريغ معلم من حصص الجدول.

        Args:
            school: كائن المدرسة
            teacher: المعلم المُفرَّغ
            academic_year: العام الدراسي
            exemption_type: نوع التفريغ (full_day / single_period)
            day_of_week: اليوم
            period_number: رقم الحصة (None لكامل اليوم)
            reason: سبب التفريغ
            created_by: المستخدم الذي أضاف التفريغ
            source: جهة القرار

        Returns:
            TeacherExemption: سجل التفريغ

        Raises:
            ValidationError: حصّةٌ بعينها بلا رقمها.

        ويُستدعى `full_clean()` هنا عمداً: `objects.create()` لا يُشغّل
        `clean()`، فلو اكتفينا به لصار في النظام بابانِ لحقيقةٍ واحدة.
        """
        exemption = TeacherExemption(
            school=school,
            teacher=teacher,
            academic_year=academic_year,
            exemption_type=exemption_type,
            day_of_week=day_of_week,
            period_number=int(period_number) if period_number else None,
            reason=reason,
            source=source,
            created_by=created_by,
        )
        exemption.full_clean(exclude=["created_by"])
        exemption.save()
        logger.info(
            "تفريغ جديد: معلم=%s نوع=%s يوم=%d بواسطة=%s",
            teacher.full_name,
            exemption_type,
            day_of_week,
            created_by.full_name if created_by else "—",
        )
        return exemption

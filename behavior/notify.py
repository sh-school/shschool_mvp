"""إشعارُ وليّ الأمر بمخالفةٍ بعد التزامها — الطبرُ واحتواءُ فشله في موضعٍ واحد.

كان في `behavior/views.py` حين لم يستدعِه غيرُ شاشتَي المخالفة. ثمّ صار كشفُ الحصص
يُبلغ الأسرةَ بالهروب من المدرسة بالمسار نفسِه (`behavior/digest.py`، 2026-09-16)،
والخدمةُ لا تستورد شاشة — فانتقل إلى هنا، وبقي اسمُه القديم في الشاشات.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from behavior.models import BehaviorInfraction
    from core.models import CustomUser, School

logger = logging.getLogger(__name__)


def notify_behavior_after_commit(
    infraction: BehaviorInfraction, school: School, reporter: CustomUser
) -> None:
    """[B4-PRE3] إشعار وليّ الأمر بمخالفة — بعد أن تُصبح المخالفة نهائية.

    هذان المساران يُطابران المهمّة مباشرةً لا عبر `NotificationHub`، فلا يشملهما
    التأجيل الذي أُدخل في B4-PRE2. ووضعُ حدٍّ معامليّ حول إنشاء المخالفة بلا
    تأجيل هذا الطبر كان سيُعيد العطب نفسه من باب آخر: طبرٌ داخل معاملة مفتوحة،
    ومع `CELERY_TASK_ALWAYS_EAGER` إرسالٌ فعليّ قبل الالتزام.

    و[B4-7A.3] الـ`except` يبقى **داخل** الـcallback لأن فشل النشر يقع بعد
    الالتزام، فلا يبلغه `except` خارجه أصلاً. وما يحرسه اليوم هو الاحتواء
    والرصد في موضع الوقوع — لا ارتداد متزامن: الإشعار لا يُعاد تنفيذه من
    الويب، والفشل يُسجَّل ولا يُعوَّض.
    """
    try:
        # [B4-7A.3] `OperationalError` هو ما يرفعه Kombu فعلاً عند سقوط الوسيط،
        # ونسبُه `KombuError → Exception` — خارج الثلاثة الأخرى تماماً. فبدونه
        # كان الاستثناء يخرج من هنا، فتضيع رسالتنا ويصير الرصد سطراً عامّاً من
        # Django لا يذكر مخالفةً ولا إشعاراً. أُثبت ذلك سلوكياً قبل الإضافة.
        from kombu.exceptions import OperationalError

        from notifications.tasks import notify_behavior_task

        notify_behavior_task.delay(
            infraction_id=str(infraction.id),
            reporter_id=str(reporter.id),
            school_id=str(school.id),
        )
    except (ImportError, OSError, RuntimeError, OperationalError):
        # [B4-7A.3] لا ارتداد متزامن — الفشل يُرصد ولا يُعوَّض هنا.
        #
        # كان هذا الموضع يستدعي `BehaviorService.notify_parents` مباشرةً، وهي
        # تعود إلى `NotificationHub`، والـHub بدوره يرتدّ إلى `_send_sync` —
        # فينتهي الأمر بنداءات مزوّد داخل طلب HTTP، بلا مهلة ولا إعادة ولا
        # استئجار ولا شيء ممّا بنيناه في B4-5/B4-6.
        #
        # وأخطر من البطء: فشلُ النشر **غامض**. قد يكون الوسيط قبِل الرسالة ثم
        # انقطع الاتصال قبل الإقرار — فيعمل العامل والويب معاً، ويصل الإشعار
        # مرّتين، ويُكتب صفّا `InAppNotification` لحدثٍ واحد. ولا سياج يمنع ذلك
        # في هذا المسار القديم: لا `NotificationDispatch` ولا استحواذ.
        #
        # فنختار خسارة محاولة إشعار نادرة عند عطل الوسيط على تكرارٍ يكسر
        # الدلالة. و`logger.error` — لا `warning` — لأن `LoggingIntegration`
        # يرفع `ERROR` فأعلى إلى Sentry، فيصير العطل مرئياً لا مدفوناً.
        logger.error(
            "broker publish failed — إشعار المخالفة %s لم يُطابر ولن يُرسل",
            infraction.pk,
            exc_info=True,
        )

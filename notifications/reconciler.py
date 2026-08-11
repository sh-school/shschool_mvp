"""[B4-4] المُصالِح — من يُغلق ما تركه الطبر مفتوحاً.

قبل هذه الدفعة كانت السلسلة تعرف أن شيئاً لم يخرج ولا تفعل به شيئاً: تسليمٌ
`pending` لأن الوسيط سقط، و`in_progress` لأن العامل مات، و`retry_wait` لأن
`self.retry()` لم تصل إلى الوسيط. ثلاثتها تبقى إلى الأبد بلا قارئ.

وهذا الملفّ هو ما جعل PRE4 شرطاً قبله: إعادة الطبر تحتاج نصّاً، والنصّ صار في
`NotificationEnqueueIntent` بدل إغلاق مات مع الطلب.

**التصنيف هو العقد كلّه:**

    قابلٌ للاسترداد        pending قديمة، retry_wait يتيمة
    لا يُسترَدّ أبداً       in_progress منقضية، sent, dead_lettered,
                           undeliverable, unknown_outcome

والحدّ بين الصنفين ليس عمر الصفّ بل **هل دخل عاملٌ منطقة المزوّد**. `pending`
لم يدخلها أحد، فأسوأ ما تُنتج إعادةُ طبرها رسالةٌ مكرّرة في الوسيط يحتملها سياج
التسليم. أمّا `in_progress` المنقضية فقد يكون المزوّد قبِل رسالتها قبل موت
العامل — وإعادتها مقامرةٌ برسالة مكرّرة تصل إلى إنسان.

ولا نحاول التمييز بين "الوسيط لم يستلم" و"استلم ثم مات المنتج". السلامة لا
تحتاج ذلك التمييز: الحدّ الذي يحمي هو حالة التسليم نفسها، والاستحواذ الذرّي
يمنع مالكَين على صفّ واحد مهما تكرّرت الرسالة في الوسيط.

**والنطاق مدرسةٌ واحدة لكل استدعاء**، لا لتقسيم الحمل بل لأن السياق المستأجَر
يُضبط لمدرسة واحدة: مُصالِحٌ يعبر المدارس في نداءٍ واحد يحتاج إمّا تجاوز RLS
وإمّا تبديل السياق داخل الحلقة — والأول يهدم الحدّ، والثاني يجعل خطأً واحداً
يترك السياق على مدرسة غير التي يظنّها المستدعي.
"""

import logging
from datetime import timedelta

from django.conf import settings
from django.db.models import Q
from django.utils import timezone

from .delivery_state import TERMINAL, mark_unknown_outcome
from .models import NotificationDelivery, NotificationEnqueueIntent

logger = logging.getLogger(__name__)

#: الحالات التي يعيد المُصالِح طبرها — ولا شيء غيرها.
RECOVERABLE = ("pending", "retry_wait")


def reconcile_school(school_id, *, now=None, limit=None):
    """يُصالح مدرسةً واحدة، ويُعيد ملخّصاً لما فعله.

    الترتيب مقصود: تُغلق المنقضية أولاً، ثم يُعاد طبر ما يستحقّ، ثم يُمسح محتوى
    ما اكتمل. لو مسحنا قبل إعادة الطبر لأزلنا النصّ الذي تحتاجه.
    """
    now = now or timezone.now()
    limit = limit or settings.NOTIFICATION_RECONCILER_BATCH_SIZE

    summary = {
        "unknown_outcome": close_expired_leases(school_id, now=now, limit=limit),
        "requeued": requeue_stale_deliveries(school_id, now=now, limit=limit),
        "scrubbed": scrub_completed_intents(school_id, now=now, limit=limit),
    }

    logger.info("Reconciler school=%s %s", school_id, summary)
    return summary


# ═══════════════════════════════════════════════════════════════════
#  ١ — الاستئجار المنقضي: إعلانٌ لا استرداد
# ═══════════════════════════════════════════════════════════════════


def close_expired_leases(school_id, *, now=None, limit=None):
    """يُعلن `unknown_outcome` عن كل `in_progress` انقضى استئجاره.

    هذه هي الحالة الوحيدة التي يكتبها المُصالِح على تسليم، ولا يُعيد بعدها
    إرسالاً أبداً. والإغلاق ليس إصلاحاً بل **إخراجٌ من الأتمتة**: الصفّ يتوقّف
    عن الظهور في كل مسحٍ لاحق، ويصير قابلاً للعرض على إنسان يقرّر.
    """
    now = now or timezone.now()
    limit = limit or settings.NOTIFICATION_RECONCILER_BATCH_SIZE

    expired = list(
        NotificationDelivery.objects.filter(
            school_id=school_id,
            status="in_progress",
            lease_expires_at__lte=now,
        ).values_list("id", flat=True)[:limit]
    )

    # واحداً واحداً لا دفعةً: كل صفّ يُعاد فحص شرطه لحظة الكتابة، فعاملٌ عاد
    # وأنهى تسليمه بين الاستعلام والتحديث يفوز — وهو الأصحّ، لأنه يعرف النتيجة
    # ونحن لا نعرفها.
    return sum(
        1 for delivery_id in expired if mark_unknown_outcome(delivery_id, school_id, now=now)
    )


# ═══════════════════════════════════════════════════════════════════
#  ٢ — إعادة الطبر: معياران معاً لا واحد
# ═══════════════════════════════════════════════════════════════════


def eligibility_filter(now):
    """المعيار المزدوج — من جهة النيّة، لأنها وحدة الطبر.

    **عمرُ التسليم وحده** كان سيُعيد الطبر بعد كل فشل مباشرةً: الفشل لا يُحرّك
    `status_changed_at`، فالصفّ يبدو قديماً أبداً — حلقةٌ ساخنة تُغرق الوسيط.

    **وعمرُ آخر محاولة وحده** كان سيلتقط صفّاً طُبر قبل ثانية ولم يبلغه العامل
    بعد، فيُنتج نداءً ثانياً لا داعي له.

    و`retry_wait` عتبتها أطول عمداً: العامل قرّر الإعادة وجدولها، فقد تكون
    المهمّة المؤجَّلة ما تزال في الوسيط تنتظر موعدها. عتبةٌ قصيرة هنا تجعل
    المُصالِح ينافس إعادة Celery على الصفّ نفسه.

    وشرطا كل فرع في `Q` واحد عمداً: فصلُهما يجعل Django يقبل تسليماً `pending`
    حديثاً مع تسليمٍ آخر `retry_wait` قديم كأنهما صفٌّ واحد يستوفي الشرطين.
    """
    aged = Q(
        dispatch__deliveries__status="pending",
        dispatch__deliveries__status_changed_at__lte=now
        - timedelta(seconds=settings.NOTIFICATION_PENDING_GRACE_SECONDS),
    ) | Q(
        dispatch__deliveries__status="retry_wait",
        dispatch__deliveries__status_changed_at__lte=now
        - timedelta(seconds=settings.NOTIFICATION_RETRY_WAIT_GRACE_SECONDS),
    )

    quiet = Q(last_enqueue_attempt_at__isnull=True) | Q(
        last_enqueue_attempt_at__lte=now
        - timedelta(seconds=settings.NOTIFICATION_REQUEUE_INTERVAL_SECONDS)
    )

    return aged & quiet


def requeue_stale_deliveries(school_id, *, now=None, limit=None):
    """يُعيد طبر النيّات التي لها تسليمٌ عالقٌ يستحقّ محاولة أخرى.

    الوحدة نيّةٌ لا تسليم: `hub_send` يمثّل مستلماً واحداً على عدّة قنوات، فطبرُ
    كل تسليم على حدة كان سيُنتج عدّة نداءات لنفس الشخص عن الحدث نفسه.

    ولا تُمرَّر القنوات: `_enqueue_intent_now` يشتقّها من التسليمات `pending`
    لحظتها، فما نجح بين الاستعلام والطبر لا يُعاد. والاستحواذ على النيّة داخله
    يجعل مُصالِحَين متزامنَين أحدهما يخسر بلا ضرر.
    """
    from .hub import _enqueue_intent_now

    now = now or timezone.now()
    limit = limit or settings.NOTIFICATION_RECONCILER_BATCH_SIZE

    intent_ids = list(
        NotificationEnqueueIntent.objects.filter(school_id=school_id)
        .filter(eligibility_filter(now))
        .values_list("id", flat=True)
        .distinct()[:limit]
    )

    return sum(1 for intent_id in intent_ids if _enqueue_intent_now(str(intent_id), str(school_id)))


# ═══════════════════════════════════════════════════════════════════
#  ٣ — مسح المحتوى: بعد أن ينتهي كل شيء
# ═══════════════════════════════════════════════════════════════════


def scrub_completed_intents(school_id, *, now=None, limit=None):
    """يمسح العنوان والنصّ من النيّات التي بلغت كل تسليماتها نهايةً.

    النصّ محفوظٌ لغرض واحد: إعادة الطبر. فإذا لم يبقَ ما يُطابر صار الاحتفاظ به
    مستودعَ محتوىً بلا وظيفة — وهذه رسائل تخصّ طلاباً وأولياء أمور، فبقاؤها بلا
    سببٍ تشغيليّ مخالفةُ تقليلِ البيانات في PDPPL لا مجرّد إسراف تخزين.

    و`unknown_outcome` تُحسب نهائية هنا رغم أنها انعدامُ معرفة: لا إعادةَ طبر
    لها أبداً، فالنصّ لا يخدم شيئاً بعدها. أمّا `pending` و`in_progress`
    و`retry_wait` فتمنع المسح — الأولى والثالثة لأنهما قد تُطابران، والثانية
    لأنها قد تصير أيّاً منهما.

    و`content_cleared_at` يبقى أثراً بأن نيّةً كانت هنا وأن محتواها أُزيل عمداً
    — الفرق بين "مُسح" و"لم يوجد" هو ما يجعل التدقيق ممكناً.
    """
    now = now or timezone.now()
    limit = limit or settings.NOTIFICATION_RECONCILER_BATCH_SIZE

    candidates = list(
        NotificationEnqueueIntent.objects.filter(
            school_id=school_id,
            content_cleared_at__isnull=True,
        )
        .exclude(
            # نيّةٌ لها تسليمٌ واحد غير نهائيّ تخرج كلّها — لا مسح جزئيّ.
            dispatch__deliveries__status__in=RECOVERABLE + ("in_progress",),
        )
        .values_list("id", "dispatch_id")[:limit]
    )

    scrubbed = 0

    for intent_id, dispatch_id in candidates:
        # فحصٌ ثانٍ لحظة الكتابة: تسليمٌ عاد إلى `in_progress` بين الاستعلام
        # والمسح يعني نصّاً ما زال مطلوباً.
        still_open = NotificationDelivery.objects.filter(
            dispatch_id=dispatch_id,
            school_id=school_id,
        ).exclude(status__in=TERMINAL)

        if still_open.exists():
            continue

        scrubbed += NotificationEnqueueIntent.objects.filter(
            id=intent_id,
            school_id=school_id,
            content_cleared_at__isnull=True,
        ).update(title=None, body=None, content_cleared_at=now)

    return scrubbed

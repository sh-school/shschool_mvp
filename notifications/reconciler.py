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
from django.db.models import Exists, OuterRef, Q
from django.utils import timezone

from .delivery_state import TERMINAL, mark_budget_exhausted, mark_unknown_outcome
from .models import NotificationDelivery, NotificationEnqueueIntent
from .tasks import _to_dlq

logger = logging.getLogger(__name__)

#: الحالات التي يعيد المُصالِح طبرها — ولا شيء غيرها.
RECOVERABLE = ("pending", "retry_wait")


def reconcile_school(school_id, *, now=None, limit=None):
    """يُصالح مدرسةً واحدة، ويُعيد ملخّصاً لما فعله.

    الترتيب مقصود لا تجميليّاً:

        ١  تُغلق المنقضية      فلا تُحسب لاحقاً على أنها قابلة للاسترداد
        ٢  تُميت المستنفدة     فلا تُطابر محاولةً أخيرة بلا معنى
        ٣  يُعاد طبر ما يستحقّ
        ٤  يُمسح ما اكتمل      وقد صار الآن يشمل ما أُغلق في ١ و٢

    ولو مسحنا قبل إعادة الطبر لأزلنا النصّ الذي تحتاجه.
    """
    now = now or timezone.now()
    limit = limit or settings.NOTIFICATION_RECONCILER_BATCH_SIZE

    summary = {
        "unknown_outcome": close_expired_leases(school_id, now=now, limit=limit),
        "exhausted": close_exhausted_deliveries(school_id, now=now, limit=limit),
        "requeued": requeue_stale_deliveries(school_id, now=now, limit=limit),
        "scrubbed": scrub_completed_intents(school_id, now=now, limit=limit),
    }

    saturated = _warn_on_saturation(school_id, summary, limit)

    # [B4-7P] حقولٌ مسمّاة لا قاموسٌ مطبوع: السطر يُقرأ ويُبحَث فيه، ولا يحمل
    # إلا مُعرِّفاً وأعداداً — لا اسم ولا عنوان ولا نصّ.
    logger.info(
        "reconcile school_id=%s unknown_outcome=%d exhausted=%d requeued=%d "
        "scrubbed=%d batch=%d saturated=%s",
        school_id,
        summary["unknown_outcome"],
        summary["exhausted"],
        summary["requeued"],
        summary["scrubbed"],
        limit,
        ",".join(saturated) or "none",
    )

    return summary


def _warn_on_saturation(school_id, summary, limit):
    """[B4-7P] تحذيرٌ لكل مرحلةٍ بلغت حدّ الدفعة — ويُعيد أسماءها.

    بلوغُ الحدّ لا يعني فشلاً، بل أن العمل **تجاوز ما تسع له مسحةٌ واحدة**: ما
    زاد لا يُفقد بل يتأخّر إلى المسحة التالية. لكنه إن تكرّر فالتراكم يسبق
    المعالجة، وهي الحالة التي لا تظهر في أي عدّاد آخر — كل مسحةٍ تبدو ناجحة
    وهي تُخلّف وراءها أكثر ممّا تُنجز.

    وتحذيرٌ لكل مرحلة لا واحدٌ عامّ: «المُصالِح مشبع» لا يقول أين، والمراحل
    الأربع لها أسبابٌ مختلفة تماماً — تشبّع `requeued` يعني وسيطاً يسقط، وتشبّع
    `scrubbed` يعني تراكم محتوىً لم يُمسح. وعلاجهما مختلف.
    """
    saturated = [stage for stage, count in summary.items() if count >= limit]

    for stage in saturated:
        logger.warning(
            "reconcile saturated school_id=%s stage=%s count=%d batch=%d",
            school_id,
            stage,
            summary[stage],
            limit,
        )

    return saturated


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
#  ٢ — الميزانية المستنفدة: حدٌّ دائم لا حدُّ رسالة
# ═══════════════════════════════════════════════════════════════════


def close_exhausted_deliveries(school_id, *, now=None, limit=None):
    """يُميت الرسائل التي استنفدت ميزانيتها الدائمة ولم يُغلقها عامل.

    الطريق الطبيعي أن يقرّر العامل الاستنفاد بنفسه في `_tracked_failure`. لكن
    عاملاً مات بعد كتابة `retry_wait` وقبل نشر إعادته يترك صفّاً استنفد ميزانيته
    ولا يعرف أحدٌ ذلك — فلو اكتفينا بالعامل لأعاد المُصالِح طبره إلى الأبد، أو
    لأنفق محاولةً أخيرة عند المزوّد بلا معنى ليكتشف ما هو معروف سلفاً.

    وهذا هو الموضع الذي يجعل الميزانية **دائمة** بحقّ: حدٌّ يُطبَّق حتى حين لا
    يوجد عاملٌ حيٌّ ليُطبّقه.
    """
    now = now or timezone.now()
    limit = limit or settings.NOTIFICATION_RECONCILER_BATCH_SIZE

    exhausted = list(
        NotificationDelivery.objects.filter(
            school_id=school_id,
            status__in=RECOVERABLE,
            attempt_count__gte=settings.NOTIFICATION_MAX_DELIVERY_ATTEMPTS,
        ).values_list("id", "channel", "dispatch_id")[:limit]
    )

    closed = 0

    for delivery_id, channel, dispatch_id in exhausted:
        # الانتقال يكتبه مالك الحالة لا المُصالِح — وهو يُعيد فحص الشرط لحظة
        # الكتابة، فصفٌّ استحوذ عليه عاملٌ في هذه الأثناء يبقى له.
        if not mark_budget_exhausted(delivery_id, school_id, now=now):
            continue

        _to_dlq(
            channel,
            school_id,
            {"dispatch_id": str(dispatch_id), "reason": "attempt_budget_exhausted"},
            "استنفدت الميزانية الدائمة بلا عاملٍ يُغلقها",
            delivery_id=str(delivery_id),
        )
        closed += 1

    return closed


# ═══════════════════════════════════════════════════════════════════
#  ٣ — إعادة الطبر: معياران معاً لا واحد
# ═══════════════════════════════════════════════════════════════════


def eligible_delivery_exists(now):
    """المعيار المزدوج كـ`Exists` مرتبطٍ بنفس المستلم.

    **الارتباط بالمستلم ليس تفصيلاً.** هوية النيّة `(dispatch, recipient)`،
    والواقعة الواحدة تحمل عدّة مستلمين. فالانضمام عبر `dispatch__deliveries`
    وحده يجعل تسليم «أ» القديم يُؤهّل نيّة «ب»، فيُطابر `_enqueue_intent_now`
    تسليم «ب» الحديث وهو في مهلته — وتسقط `PENDING_GRACE` عملياً في كل واقعة
    متعدّدة المستلمين.

    **وعمرُ التسليم وحده** كان سيُعيد الطبر بعد كل فشل مباشرةً: الفشل لا يُحرّك
    `status_changed_at`، فالصفّ يبدو قديماً أبداً — حلقةٌ ساخنة تُغرق الوسيط.

    **وعمرُ آخر محاولة وحده** كان سيلتقط صفّاً طُبر قبل ثانية ولم يبلغه العامل
    بعد، فيُنتج نداءً ثانياً لا داعي له.

    و`retry_wait` عتبتها أطول عمداً: العامل قرّر الإعادة وجدولها، فقد تكون
    المهمّة المؤجَّلة ما تزال في الوسيط تنتظر موعدها.

    والمستنفدة ميزانيتها مستبعَدة هنا: تُغلق في مرحلةٍ سابقة، فلا تُطابر مرّةً
    أخيرة بلا معنى.
    """
    correlated = NotificationDelivery.objects.filter(
        dispatch_id=OuterRef("dispatch_id"),
        recipient_id=OuterRef("recipient_id"),
        school_id=OuterRef("school_id"),
        attempt_count__lt=settings.NOTIFICATION_MAX_DELIVERY_ATTEMPTS,
    ).filter(
        Q(
            status="pending",
            status_changed_at__lte=now
            - timedelta(seconds=settings.NOTIFICATION_PENDING_GRACE_SECONDS),
        )
        | Q(
            status="retry_wait",
            status_changed_at__lte=now
            - timedelta(seconds=settings.NOTIFICATION_RETRY_WAIT_GRACE_SECONDS),
        )
    )

    quiet = Q(last_enqueue_attempt_at__isnull=True) | Q(
        last_enqueue_attempt_at__lte=now
        - timedelta(seconds=settings.NOTIFICATION_REQUEUE_INTERVAL_SECONDS)
    )

    return Q(Exists(correlated)) & quiet


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
        .filter(eligible_delivery_exists(now))
        .values_list("id", flat=True)[:limit]
    )

    return sum(1 for intent_id in intent_ids if _enqueue_intent_now(str(intent_id), str(school_id)))


# ═══════════════════════════════════════════════════════════════════
#  ٤ — مسح المحتوى: بعد أن ينتهي كل شيء
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

    والنطاق تسليمات **هذا المستلم** لا الواقعة كلّها: العقد "كل تسليمات النيّة"،
    وهويّتها `(dispatch, recipient)`. الفحص على الواقعة وحدها كان يُبقي محتوى
    مستلمٍ انتهى أمرُه محفوظاً لأن مستلماً آخر ما زال مفتوحاً — أثرُه محافظ لا
    خطير، لكنه يُطيل بقاء المحتوى بلا سبب، وهو عكس ما يخدمه المسح أصلاً.
    """
    now = now or timezone.now()
    limit = limit or settings.NOTIFICATION_RECONCILER_BATCH_SIZE

    open_for_recipient = NotificationDelivery.objects.filter(
        dispatch_id=OuterRef("dispatch_id"),
        recipient_id=OuterRef("recipient_id"),
        school_id=OuterRef("school_id"),
    ).exclude(status__in=TERMINAL)

    candidates = list(
        NotificationEnqueueIntent.objects.filter(
            school_id=school_id,
            content_cleared_at__isnull=True,
        )
        .filter(~Q(Exists(open_for_recipient)))
        .values_list("id", "dispatch_id", "recipient_id")[:limit]
    )

    scrubbed = 0

    for intent_id, dispatch_id, recipient_id in candidates:
        # فحصٌ ثانٍ لحظة الكتابة: تسليمٌ عاد إلى `in_progress` بين الاستعلام
        # والمسح يعني نصّاً ما زال مطلوباً.
        still_open = (
            NotificationDelivery.objects.filter(
                dispatch_id=dispatch_id,
                recipient_id=recipient_id,
                school_id=school_id,
            )
            .exclude(status__in=TERMINAL)
            .exists()
        )

        if still_open:
            continue

        scrubbed += NotificationEnqueueIntent.objects.filter(
            id=intent_id,
            school_id=school_id,
            content_cleared_at__isnull=True,
        ).update(title=None, body=None, content_cleared_at=now)

    return scrubbed

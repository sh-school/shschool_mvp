"""[B4-PRE4] المالك الوحيد لاستئجار الطبر.

قفلٌ مستقلّ عن استئجار التسليم، ولا يُستعمل أحدهما مكان الآخر. المعنى مختلف:

    Delivery lease        ملكيّةُ تنفيذٍ عند المزوّد
    EnqueueIntent lease   ملكيّةُ محاولةِ إدخال العمل إلى الوسيط

ولو استعمل المُصالِح `claim_delivery` لمعالجة تسليم معلّق لصار الصفّ
`in_progress` قبل أن تصل المهمّة إلى العامل، فيرفض العاملُ تنفيذها — قفلٌ
يمنع العمل الذي جُلب لأجله.

**والانقضاء هنا قابل للاستحواذ ثانيةً**، خلافاً لاستئجار التسليم: عاملٌ فُقد
أثناء الطبر لا يترك احتمالاً بأن المزوّد استقبل شيئاً. وأسوأ ما يقع أن يكون
الوسيط قد استلم الرسالة ثم مات المنتج قبل تسجيل ذلك، فتُعاد رسالةٌ في الوسيط —
وسياج التسليم مصمَّم لاحتمال ذلك بالضبط:

    رسالة مكرّرة في الوسيط     مقبولة
    تنفيذ مكرّر عند المزوّد     ممنوع بالسياج
"""

import uuid
from datetime import timedelta

from django.conf import settings
from django.db.models import Q
from django.utils import timezone

from .models import NotificationEnqueueIntent


def claim_enqueue_intent(intent_id, school_id, *, now=None, lease_seconds=None):
    """يستحوذ على محاولة طبر واحدة، ويُعيد رمز السياج — أو `None`.

    يُرفض حين يملكها منتجٌ آخر واستئجاره ما زال حيّاً. أمّا المنقضي فيُستحوَذ
    عليه — انظر ملاحظة الوحدة أعلاه.
    """
    now = now or timezone.now()
    seconds = (
        settings.NOTIFICATION_ENQUEUE_LEASE_SECONDS if lease_seconds is None else lease_seconds
    )

    if seconds <= 0:
        raise ValueError(f"lease_seconds يجب أن تكون موجبة — {seconds}")

    token = uuid.uuid4()

    claimed = (
        NotificationEnqueueIntent.objects.filter(id=intent_id, school_id=school_id)
        .filter(Q(enqueue_expires_at__isnull=True) | Q(enqueue_expires_at__lte=now))
        .update(
            enqueue_token=token,
            enqueue_expires_at=now + timedelta(seconds=seconds),
        )
    )

    return token if claimed == 1 else None


def finish_enqueue_attempt(intent_id, school_id, token, *, now=None):
    """يُسجّل أن محاولة طبر جرت — نجحت أم فشلت — ويُفرّغ الاستئجار.

    الزمن يُكتب في الحالتين: مُصالِحٌ يقيس بـ`status_changed_at` وحده سيُعيد
    الطبر فوراً بعد فشلٍ، لأن التسليم لم ينتقل. `last_enqueue_attempt_at` هي
    ما يمنع الحلقة الساخنة.
    """
    now = now or timezone.now()

    finished = NotificationEnqueueIntent.objects.filter(
        id=intent_id,
        school_id=school_id,
        enqueue_token=token,
    ).update(
        last_enqueue_attempt_at=now,
        enqueue_token=None,
        enqueue_expires_at=None,
    )

    return finished == 1

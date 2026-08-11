"""[B4-3A] المالك الوحيد لحالة `NotificationDelivery` واستئجارها.

لا شيء خارج هذا الملفّ يكتب `status` ولا `lease_token` ولا `lease_expires_at`.
المهامّ الأربع تنفّذ التسليم؛ وملكيّة الحالة طبقةٌ مستقلّة عنها، وإلا تكرّر
منطق الاستحواذ أربع مرّات وانحرفت نسخة عن أخرى في الدفعة التي لا ينتبه فيها
أحد.

**الاستحواذ ذرّي**: `UPDATE ... WHERE status IN (...)` بنداء واحد، لا قراءةً ثم
كتابة. الصيغة الثانية تترك نافذةً بين الفحص والتعديل يمرّ منها عاملان فيظنّ
كلٌّ منهما أنه المالك.

**والإنهاء مُسيَّج**: لا يكفي أن يكون التسليم `in_progress`؛ يجب أن يحمل العامل
الرمز نفسه وأن يكون الاستئجار **حيّاً**. عاملٌ بطيء يعود بعد انقضاء ملكيّته لا
يكتب شيئاً — وإلا سبق المُصالِح إلى الصفّ وكتب `sent` عن نتيجة لم يعد يعرفها.

وما ينقضي استئجاره يبقى `in_progress` في هذه المرحلة. لا استحواذ جديد عليه ولا
إعادة تلقائية: عاملٌ مات بعد أن قبِل المزوّد الرسالة لا يترك ما يقول إن كانت
وصلت، فإعادةُ الإرسال احتمالُ تكرار حقيقي. تفسيرُ ذلك الصفّ وسياسةُ استرداده
شأن المُصالِح في B4-4 — وبقاؤه عالقاً حتى ذلك الحين هو نفسه الدليل على أن
المُصالِح شرطٌ قبل أي تفعيل إنتاجي.
"""

import uuid
from datetime import timedelta

from django.conf import settings
from django.utils import timezone

from .models import NotificationDelivery

#: الحالات التي يجوز الاستحواذ منها — بدايةٌ أو انتظارُ إعادة.
CLAIMABLE = ("pending", "retry_wait")

#: النهايات التي تستطيع هذه المرحلة تمثيلها.
#:
#: `undeliverable` تنتظر B4-3B لأنها هناك يُنتجها Push بلا اشتراكات، و
#: `unknown_outcome` تنتظر B4-4 لأن العامل الميت لا يقول إنه مات — يكتشفه غيره.
FINALIZABLE = ("sent", "retry_wait", "dead_lettered")


def claim_delivery(delivery_id, school_id, *, now=None, lease_seconds=None):
    """يستحوذ على التسليم لتنفيذ واحد، ويُعيد رمز السياج — أو `None`.

    `None` تعني أن الاستحواذ رُفض: التسليم انتهى، أو يملكه تنفيذ آخر، أو ليس
    لهذه المدرسة. والرفض ليس خطأً بل الجواب المطلوب — عاملان على صفّ واحد
    أحدهما يخسر.

    والمدرسة شرطٌ صريح رغم وجود RLS: الاعتماد على أن المُعرِّف وحده لن يقود إلى
    مستأجر آخر يجعل التوقّع ضمنياً في مكان يجب أن يكون فيه مكتوباً.
    """
    now = now or timezone.now()

    # `lease_seconds or settings...` كان يُخفي حالتين: الصفر قيمة كاذبة فيتحوّل
    # صامتاً إلى الافتراضي بدل أن يُرفض، والسالب قيمة صادقة فيُقبل — فيُنشئ
    # استئجاراً منتهياً لحظة إنشائه. وفحصُ الإعداد في `settings` لا يبلغ
    # مُستدعياً يُمرّر القيمة مباشرةً.
    seconds = (
        settings.NOTIFICATION_DELIVERY_LEASE_SECONDS if lease_seconds is None else lease_seconds
    )

    if seconds <= 0:
        raise ValueError(
            f"lease_seconds يجب أن تكون موجبة — {seconds} تُنشئ استئجاراً منتهياً فور إنشائه"
        )

    token = uuid.uuid4()

    claimed = NotificationDelivery.objects.filter(
        id=delivery_id,
        school_id=school_id,
        status__in=CLAIMABLE,
    ).update(
        status="in_progress",
        lease_token=token,
        lease_expires_at=now + timedelta(seconds=seconds),
        status_changed_at=now,
    )

    return token if claimed == 1 else None


def finalize_delivery(delivery_id, school_id, token, status, *, now=None):
    """يُنهي تسليماً يملكه حاملُ هذا الرمز ولم ينقضِ استئجاره.

    يُعيد `True` إن كُتب الانتقال، و`False` إن لم يُطابق شيء — وهي حالة عاملٍ
    فقد ملكيّته. عندها **لا يكتب شيئاً**: ليس فشلاً في الإرسال بل فقداناً
    للسلطة على الصفّ.
    """
    if status not in FINALIZABLE:
        raise ValueError(f"{status} ليست نهايةً تستطيع هذه المرحلة كتابتها — المسموح {FINALIZABLE}")

    now = now or timezone.now()

    finalized = NotificationDelivery.objects.filter(
        id=delivery_id,
        school_id=school_id,
        status="in_progress",
        lease_token=token,
        lease_expires_at__gt=now,
    ).update(
        status=status,
        lease_token=None,
        lease_expires_at=None,
        status_changed_at=now,
    )

    return finalized == 1

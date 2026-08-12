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
from django.db.models import F
from django.utils import timezone

from .models import NotificationDelivery

#: الحالات التي يجوز الاستحواذ منها — بدايةٌ أو انتظارُ إعادة.
CLAIMABLE = ("pending", "retry_wait")

#: النهايات التي يكتبها **العامل** تحت السياج.
#:
#: `unknown_outcome` ليست منها عمداً: العامل الميت لا يقول إنه مات — يكتشفه
#: غيره، فكاتبها `mark_unknown_outcome` وحدها.
FINALIZABLE = ("sent", "retry_wait", "dead_lettered", "undeliverable")

#: [B4-4] ما لا يُلمس بعد بلوغه — لا استرداد ولا إعادة طبر.
#:
#: `unknown_outcome` هنا رغم أنها ليست نجاحاً: النهائية هنا نهائيةُ **أتمتة**
#: لا نهائيةُ معرفة. وإخراجُها من الأتمتة هو بالضبط ما يجعلها قابلة للعرض على
#: إنسان يقرّر.
TERMINAL = ("sent", "dead_lettered", "undeliverable", "unknown_outcome")


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
        # [B4-4] الاستحواذ **هو** المحاولة، فالعدّ يقع هنا لا عند النتيجة:
        # عاملٌ مات بعد نداء المزوّد وقبل كتابة أي شيء يكون قد استهلك محاولةً
        # فعلاً — ولو عددنا عند النهاية لما ظهرت تلك المحاولة أبداً.
        #
        # و`F` لا قراءة-ثمّ-كتابة: عاملان لا يستحوذان معاً، لكن العدّاد يشترك
        # مع المُصالِح ومع كلّ من يقرأ الصفّ، والزيادة في القاعدة لا تفقد شيئاً.
        attempt_count=F("attempt_count") + 1,
    )

    return token if claimed == 1 else None


def attempts_used(delivery_id, school_id):
    """[B4-4] الميزانية المستهلكة — من القاعدة لا من كائنٍ قديم في الذاكرة.

    الكائن الذي حلّته المهمّة قبل الاستحواذ يحمل عدّاداً سابقاً للزيادة، فقراءته
    منه تُنقص واحداً دائماً — وهي بالضبط الواحدة التي تفصل الاستنفاد عن دورةٍ
    إضافية.
    """
    return (
        NotificationDelivery.objects.filter(id=delivery_id, school_id=school_id)
        .values_list("attempt_count", flat=True)
        .first()
        or 0
    )


def budget_exhausted(delivery_id, school_id):
    """هل استُنفدت ميزانية هذا التسليم الدائمة؟"""
    return attempts_used(delivery_id, school_id) >= settings.NOTIFICATION_MAX_DELIVERY_ATTEMPTS


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


def mark_unknown_outcome(delivery_id, school_id, *, now=None):
    """[B4-4] يُغلق تسليماً انقضى استئجاره وهو `in_progress` — بلا استرداد.

    هذا هو الانتقال الوحيد الذي يكتبه المُصالِح على تسليم، وأخطر ما في السلسلة.

    الشرط `lease_expires_at <= now` ليس تفصيلاً: عاملٌ استئجاره حيٌّ قد يكون في
    منتصف نداء المزوّد، وسحبُ الصفّ من تحته يجعل نهايته المُسيَّجة ترتدّ فتضيع
    نتيجةٌ كانت معروفة. والانقضاء وحده هو ما يسمح بهذا الإعلان.

    ولا رمز يُشترط: المُصالِح ليس مالك الاستئجار بل من يُعلن أن مالكه لم يعد
    موجوداً — فاشتراطُ رمزٍ لا يملكه أحدٌ حيّ يجعل الانتقال غير قابل للكتابة.
    """
    now = now or timezone.now()

    marked = NotificationDelivery.objects.filter(
        id=delivery_id,
        school_id=school_id,
        status="in_progress",
        lease_expires_at__lte=now,
    ).update(
        status="unknown_outcome",
        lease_token=None,
        lease_expires_at=None,
        status_changed_at=now,
    )

    return marked == 1


def mark_budget_exhausted(delivery_id, school_id, *, now=None):
    """[B4-4] يُميت تسليماً استنفد ميزانيته الدائمة ولا عاملَ حيٌّ يُغلقه.

    الطريق الطبيعي أن يقرّر العامل الاستنفاد في `_tracked_failure` تحت سياجه.
    لكن عاملاً مات بعد كتابة `retry_wait` وقبل نشر إعادته يترك صفّاً استنفد
    ميزانيته ولا يعرف أحدٌ ذلك — فهذا هو الموضع الذي يجعل الميزانية دائمةً
    بحقّ: حدٌّ يُطبَّق حتى حين لا يوجد من يُطبّقه.

    والشرط يُعاد فحصه لحظة الكتابة: صفٌّ استحوذ عليه عاملٌ بين قرار المُصالِح
    وكتابته يخرج من `CLAIMABLE`، وله مالكٌ يعرف نتيجته أكثر منّا.
    """
    now = now or timezone.now()

    killed = NotificationDelivery.objects.filter(
        id=delivery_id,
        school_id=school_id,
        status__in=CLAIMABLE,
        attempt_count__gte=settings.NOTIFICATION_MAX_DELIVERY_ATTEMPTS,
    ).update(
        status="dead_lettered",
        lease_token=None,
        lease_expires_at=None,
        status_changed_at=now,
    )

    return killed == 1


def mark_undeliverable(delivery_id, school_id, *, now=None):
    """[B4-3B] يُنهي تسليماً لم تبدأ له منطقة مزوّد أصلاً.

    مسارٌ مستقلّ عن الاستحواذ عمداً. المرور بـ`in_progress` هنا ادّعاءٌ بأن
    تنفيذاً جرى: مستخدم بلا اشتراكات فعّالة لا يدخل العامل معه منطقة مزوّد،
    فوسمُه "قيد التنفيذ" ثم إنهاؤه يترك في التاريخ انتقالاً لم يقع.

    أمّا الاشتراكات التي ردّ عليها المزوّد كلّها بـ404/410 فتلك محاولات جرت
    فعلاً، ونهايتها تُكتب بـ`finalize_delivery` تحت السياج كغيرها.
    """
    now = now or timezone.now()

    marked = NotificationDelivery.objects.filter(
        id=delivery_id,
        school_id=school_id,
        status__in=CLAIMABLE,
    ).update(
        status="undeliverable",
        lease_token=None,
        lease_expires_at=None,
        status_changed_at=now,
    )

    return marked == 1

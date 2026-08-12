"""[B4-5] المالك الوحيد لثابت "لا يتجاوز مستخدمٌ سقف اشتراكاته الفعّالة".

السقف ليس تنظيماً للتخزين بل **شرطُ سلامة**: تسليم Push واحد يفتح نداءً متسلسلاً
لكل اشتراك فعّال، فعددُها هو المُعامل الذي تُحسب به أسوأ حالة زمنية. وبلا حدٍّ
له تصير الميزانية غير محسوبة، وينقضي الاستئجار أثناء عملٍ مشروع.

**ولماذا الإخراج بالأقدم استعمالاً لا الرفض؟** رفضُ اشتراكٍ جديد يعني جهازاً
حقيقياً لا يصله شيء، والمستخدم لا يفهم لماذا. أمّا الأقدم استعمالاً فأرجح
المرشّحين لأن يكون متصفّحاً مهجوراً أو جهازاً استُبدل — والمتصفّح يُعيد الاشتراك
تلقائياً عند العودة. فالإخراج سياسةٌ معلومة لا حذفٌ اعتباطيّ.

**ولا يُحذف صفّ**: `is_active=False` يُبقي الأثر، وسجلّات المحاولات تشير إليه.
"""

import logging

from django.conf import settings
from django.db import transaction
from django.db.models import F

from .models import PushSubscription

logger = logging.getLogger(__name__)


def _least_recently_used():
    """`NULLS FIRST` — من لم يُستعمل قطّ أولى بالإخراج ممّن استُعمل يوماً."""
    return F("last_used").asc(nulls_first=True)


def active_subscription_cap():
    return settings.PUSH_MAX_ACTIVE_SUBSCRIPTIONS


def register_subscription(*, user, school, endpoint, p256dh, auth, user_agent=""):
    """يُسجّل اشتراكاً ويضمن ألّا تتجاوز الاشتراكات الفعّالة السقف.

    الكلّ داخل معاملة واحدة مع `select_for_update`: بلا القفل يستطيع طلبان
    متزامنان من جهازين أن يقرأ كلٌّ منهما عدداً تحت السقف ثم يكتبا معاً، فيتجاوز
    المجموع الحدَّ الذي يُفترض أنه ثابت.

    ويُعيد `(subscription, created, evicted)` — والأخير عددُ ما أُخرج، لأن
    الإخراج الصامت يجعل جهازاً يتوقّف عن تلقّي الإشعارات بلا أثر يُقرأ.
    """
    cap = active_subscription_cap()

    with transaction.atomic():
        # ── القفل على صفّ المستخدم أولاً ──────────────────────────────
        #
        # `select_for_update()` على اشتراكاته وحدها **لا يكفي**: مستخدمٌ بلا
        # اشتراكات بعدُ يُنتج مجموعةً فارغة، والقفل لا يشمل "عدم وجود صفّ".
        # فطلبان متزامنان من جهازين — وهو أوّل ما يقع عند تسجيل أول جهازين —
        # يقرأ كلٌّ منهما صفراً ثم يكتبان معاً، فيتجاوز المجموع سقفاً يُفترض
        # أنه ثابت.
        #
        # وصفّ المستخدم موجودٌ دائماً بحكم أنه المُسجِّل، فيصلح نقطةَ تسلسلٍ
        # لكل تسجيلات هذا المستخدم مهما كان عدد اشتراكاته — بما فيه الصفر.
        type(user).objects.select_for_update().get(pk=user.pk)

        # ثم قفلُ اشتراكاته القائمة — يمنع تعديلها تحت أقدامنا.
        existing = list(
            PushSubscription.objects.select_for_update()
            .filter(user=user, school=school)
            .order_by("-is_active", "-last_used", "-created_at")
        )

        current = next((row for row in existing if row.endpoint == endpoint), None)

        if current is not None:
            # اشتراكٌ معروف يُجدَّد: لا يزيد العدد الفعّال إن كان فعّالاً أصلاً.
            was_active = current.is_active
            current.p256dh = p256dh
            current.auth = auth
            current.user_agent = user_agent[:300]
            current.is_active = True
            current.save(update_fields=["p256dh", "_auth", "user_agent", "is_active"])
            created = False
            grew = not was_active
        else:
            current = PushSubscription.objects.create(
                user=user,
                school=school,
                endpoint=endpoint,
                p256dh=p256dh,
                auth=auth,
                user_agent=user_agent[:300],
                is_active=True,
            )
            created = grew = True

        evicted = 0

        if grew:
            # الأقدم استعمالاً أولاً — و`created_at` فاصلٌ لمن لم يُستعمل قطّ.
            others = list(
                PushSubscription.objects.select_for_update()
                .filter(user=user, school=school, is_active=True)
                .exclude(pk=current.pk)
                .order_by(_least_recently_used(), "created_at")
            )

            surplus = len(others) + 1 - cap

            for row in others[: max(surplus, 0)]:
                row.is_active = False
                row.save(update_fields=["is_active"])
                evicted += 1

            if evicted:
                logger.info(
                    "Push cap %d reached for user %s — %d subscription(s) deactivated (LRU)",
                    cap,
                    user.pk,
                    evicted,
                )

    return current, created, evicted

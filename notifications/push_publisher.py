"""[B4-6] الناشر الوحيد لـ`notifications.send_push`.

الحدّ الزمني اللين **يسافر في الرسالة**، لا يُقرأ من إعدادات العامل. عقد Celery:

    apply_async → extract_exec_options(task)   # يلتقط soft_time_limit
                → amqp.as_task_v2(...)         # 'timelimit': [hard, soft]
    worker      → request.py:363
                  soft_timeout = soft_time_limit or task.soft_time_limit

فالجزء الأخير يعني أمرين معاً:

    ترويسة `None`      ⇒ يسقط العامل إلى إعداده — آمن
    ترويسة صريحة       ⇒ **تتغلّب** على إعداد العامل

والخطر في الثانية وحدها. ناشرٌ يشحن `soft_time_limit=300` يجعل العامل ينتظر
خمس دقائق بينما استئجاره محسوبٌ على 120 ثانية — فينقضي الاستئجار والعامل حيٌّ،
ويكتب المُصالِح `unknown_outcome` عن حالةٍ كانت معروفة. وهي بالضبط العلّة التي
أغلقتها B4-5، تعود من باب النشر.

والمتباينة `worst < soft < lease − margin` تُفحص عند الإقلاع من **إعدادات
العملية**. فإن جاءت القيمة الفعلية من رسالة، صار الثابت موزَّعاً بين عمليتين بلا
ما يضمن تطابقهما. وهذا الملفّ هو ذلك الضمان: مصدرٌ واحد للحقيقة **عند النشر**.

ولماذا الرفض لا التصحيح الصامت؟ لأن مُستدعياً يطلب حدّاً مخالفاً إمّا مخطئ وإمّا
يعرف شيئاً لا نعرفه — وفي الحالتين إسكاتُه يُخفي المعلومة. والرفض قبل بلوغ
الوسيط يُبقي الخطأ في مكان وقوعه.
"""

import logging

from django.conf import settings

logger = logging.getLogger(__name__)

#: الوسائط التي يمنع هذا المالك تمريرها بقيمةٍ تخالف المعتمد.
_GOVERNED = ("soft_time_limit", "time_limit")


def canonical_soft_time_limit():
    """المصدر الواحد — نفس ما تفحصه `_validate_push_budget` عند الإقلاع."""
    return settings.PUSH_SOFT_TIME_LIMIT_SECONDS


def _reject_noncanonical(options):
    """يرفض قبل النشر — لا رسالة تدخل الوسيط بحدٍّ غير معتمد.

    والمطابق يُسحب من الخيارات بعد قبوله: تمريره مرّتين — هنا وفي النداء أدناه —
    يرفعه Python وسيطاً مكرّراً، فيتحوّل تصريحٌ صحيح إلى `TypeError`.
    """
    canonical = canonical_soft_time_limit()

    for name in _GOVERNED:
        if name not in options:
            continue

        value = options.pop(name)
        allowed = canonical if name == "soft_time_limit" else None

        if value != allowed:
            raise ValueError(
                f"{name}={value} يخالف المعتمد ({allowed}) لـnotifications.send_push. "
                "الحدّ يسافر في الرسالة ويتغلّب على إعداد العامل، فقيمةٌ أطول تجعل "
                "الاستئجار ينقضي والعامل حيٌّ — وهي علّة `unknown_outcome` نفسها."
            )


def enqueue_push(
    *,
    user_id,
    school_id,
    title,
    body,
    url="/parents/",
    delivery_id=None,
    **options,
):
    """ينشر `send_push` بالحدّ المعتمد — والطريق الوحيد المسموح.

    `soft_time_limit` يُمرَّر **صراحةً** لا يُترك لسمة المهمّة: السمة تُقرأ من
    إعدادات عملية الناشر، وتمريرها هنا يجعل المصدر موضعاً واحداً مقروءاً بدل
    اعتمادٍ ضمنيّ على أن كل ناشر يحمل الإعداد نفسه.
    """
    from .tasks import send_push_task

    _reject_noncanonical(options)

    return send_push_task.apply_async(
        args=(str(user_id), title, body, url),
        kwargs={"school_id": str(school_id), "delivery_id": delivery_id},
        soft_time_limit=canonical_soft_time_limit(),
        **options,
    )

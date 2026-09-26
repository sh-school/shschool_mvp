"""رموزُ أخطاء التصدير ورسائلُها العربيّةُ الثابتة — لا نصَّ استثناءٍ يخرج من الخادم أبداً.

`ExportJob.error_message` يحمل **رمزاً** (`timeout`/`too_large`/`failed`) لا رسالة: نصُّ الاستثناء قد يحمل معاملاتِ SQL
وقيمَ قوالبَ فيه بياناتٌ شخصيّة، وكان يُخزَّن (`str(exc)[:2000]`) ويُعاد للعميل. والرسالةُ تُترجَم هنا عند القراءة؛
ورمزٌ غيرُ معروفٍ (صفٌّ قديمٌ خُزّنت فيه رسالةٌ طويلة) يُعرَض `failed` فلا يتسرّب شيءٌ منه.
"""

from __future__ import annotations

TIMEOUT = "timeout"
TOO_LARGE = "too_large"
FAILED = "failed"
FORBIDDEN = "forbidden"
BUSY = "busy"
UNKNOWN_KIND = "unknown_kind"

MESSAGES = {
    TIMEOUT: (
        "انتهت مهلةُ تحضير الملفّ قبل أن يكتمل — لم يلتقط عاملُ الخلفيّة المهمّةَ أو توقّف في منتصفها. "
        "أعِد المحاولة؛ فإن تكرّر ذلك فأبلِغ مطوّرَ المنصّة."
    ),
    TOO_LARGE: "الملفُّ أكبرُ من الحدّ المسموح به. ضيِّق الاختيارَ (شعبةً أو قسماً أو فترةً) وأعِد المحاولة.",
    FAILED: "تعذّر تحضيرُ الملفّ. أعِد المحاولة؛ فإن تكرّر ذلك فأبلِغ مطوّرَ المنصّة.",
    FORBIDDEN: "لا تملك صلاحيةَ هذا التصدير.",
    BUSY: "لديك تصديراتٌ قيد التحضير بلغت الحدّ المسموح — انتظر اكتمالَ أحدها ثمّ أعِد المحاولة.",
    UNKNOWN_KIND: "نوعُ التصدير غيرُ معروف.",
}

#: رموزٌ يخزّنها العاملُ في الصفّ — ما عداها لا يُعرَض.
STORED_CODES = (TIMEOUT, TOO_LARGE, FAILED, FORBIDDEN)


def stored_code(raw: str) -> str:
    """الرمزُ الآمن لما في `error_message`: رمزٌ معروفٌ يبقى، وغيرُه (صفٌّ قديمٌ برسالةٍ طويلة) `failed`."""
    return raw if raw in STORED_CODES else FAILED


def message_for(code: str) -> str:
    return MESSAGES.get(code, MESSAGES[FAILED])


def error_payload(code: str) -> dict:
    """شكلُ الخطأ في عقد الاستجابة: `{"code": …, "message": …}` — الرسالةُ العربيّةُ الثابتةُ وحدَها."""
    return {"code": code, "message": message_for(code)}

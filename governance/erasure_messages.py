"""جملُ المحو الثابتة المشتركة بين الـAPI والشاشة (PDPPL م.18).

ردودُ التعثّر والرفض **من جدولٍ ثابتٍ** — لا يخرج نصُّ الاستثناء إلى العميل (CodeQL py/stack-trace-exposure،
قرارُ المالك: الإغلاقُ بالكود لا بالاستبعاد). رمزُ الاستثناء مفتاحٌ فقط؛ والتفصيلُ الكاملُ في AuditLog وlogger
بمعرّفٍ لا بنصّ. وهي هنا لا في `api` كي لا تستورد `governance` من طبقة الواجهة.
"""

from rest_framework import status

from governance.erasure_service import (
    ErasureAlreadySignedError,
    ErasureNoOfficerError,
    ErasureNoteRequiredError,
    ErasureNotSignerError,
    ErasureSelfApprovalError,
    ErasureStateError,
)

ERASURE_FAILURES: dict[str, tuple[str, str]] = {
    "erasure_wrong_tenant": (
        "erasure_wrong_tenant",
        "تعذّر محو سجلّ رصد المعلّم لهذا الطالب: دورُ القاعدة الحاليّ لمدرسةٍ غيرِ مدرسة الطلب — يُنفَّذ بدور مدرستها.",
    ),
    "erasure_incomplete": (
        "erasure_incomplete",
        "تعذّر محو سجلّ رصد المعلّم لهذا الطالب: بقيت صفوفٌ بعد المحو وأُلغيت المعاملة.",
    ),
    "erasure_error": (
        "erasure_error",
        "تعذّر تنفيذ المحو لخطأٍ غيرِ متوقَّع سُجّل للمراجعة.",
    ),
}
ERASURE_RETRY_NOTE = (
    "لم يُمسّ شيء. الطلبُ باقٍ «تمّت الموافقة» ويمكن إعادة التنفيذ بتوقيعين جديدين بعد معالجة السبب."
)
ERASURE_STATE_MESSAGE = "لا يمكن الموافقة — الطلبُ ليس في حالةٍ تقبل الموافقة أو التنفيذ."
ERASURE_SELF_APPROVAL_MESSAGE = "لا يوقّع مقدِّمُ طلب المحو طلبَه ولا يرفضه: يوقّعه موقّعان غيرُه."
ERASURE_SIGNED_MESSAGE = "سُجّل توقيعك — يُنفَّذ المحو عند التوقيع الثاني."

#: ردُّ كلِّ رفضٍ من الخدمة: جملةٌ ثابتةٌ ورمزُ HTTP — لا نصَّ استثناء.
ERASURE_REFUSALS: dict[type[Exception], tuple[str, int]] = {
    ErasureStateError: (ERASURE_STATE_MESSAGE, status.HTTP_400_BAD_REQUEST),
    ErasureSelfApprovalError: (ERASURE_SELF_APPROVAL_MESSAGE, status.HTTP_403_FORBIDDEN),
    ErasureNoOfficerError: (
        "لا يُنفَّذ المحو: لم يُعيَّن مسؤولُ حماية البيانات للمدرسة — يعيّنه المديرُ أوّلاً.",
        status.HTTP_409_CONFLICT,
    ),
    ErasureNotSignerError: (
        "لستَ من موقّعَي هذا الطلب: يوقّعه المدير (أو النائب الإداريّ إن كان المديرُ مقدِّمَه) "
        "ومسؤولُ حماية البيانات.",
        status.HTTP_403_FORBIDDEN,
    ),
    ErasureAlreadySignedError: (
        "التوقيعُ مسجَّلٌ من قبل — ينتظر الطلبُ الموقّعَ الآخر.",
        status.HTTP_409_CONFLICT,
    ),
    ErasureNoteRequiredError: ("سبب الرفض مطلوب.", status.HTTP_400_BAD_REQUEST),
}

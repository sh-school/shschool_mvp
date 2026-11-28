"""رسائلُ طلب المحو الثابتة — مصدرٌ واحدٌ للـAPI وشاشة الويب (U-11).

الردودُ من هذا الجدول لا من نصّ الاستثناء (CodeQL py/stack-trace-exposure): رمزُ الاستثناء مفتاحٌ فقط.
"""

from governance.erasure_service import (
    ErasureAlreadySignedError,
    ErasureNoOfficerError,
    ErasureNoteRequiredError,
    ErasureNotSignerError,
    ErasureSelfApprovalError,
    ErasureStateError,
)

#: ردودُ تعثّر المحو **ثابتةٌ من جدولٍ**؛ والتفصيلُ الكاملُ في AuditLog وlogger بمعرّفٍ لا بنصّ.
ERASURE_FAILURES = {
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
ERASURE_SIGNED_MESSAGE = "سُجّل توقيعك — يُنفَّذ المحو عند التوقيع الثاني."
ERASURE_DONE_MESSAGE = "تم تنفيذ المحو بنجاح."

#: جملةُ كلِّ رفضٍ من الخدمة.
ERASURE_REFUSAL_MESSAGES: dict[type[Exception], str] = {
    ErasureStateError: "لا يمكن الموافقة — الطلبُ ليس في حالةٍ تقبل الموافقة أو التنفيذ.",
    ErasureSelfApprovalError: "لا يوقّع مقدِّمُ طلب المحو طلبَه ولا يرفضه: يوقّعه موقّعان غيرُه.",
    ErasureNoOfficerError: "لا يُنفَّذ المحو: لم يُعيَّن مسؤولُ حماية البيانات للمدرسة — يعيّنه المديرُ أوّلاً.",
    ErasureNotSignerError: (
        "لستَ من موقّعَي هذا الطلب: يوقّعه المدير (أو النائب الإداريّ إن كان المديرُ مقدِّمَه) "
        "ومسؤولُ حماية البيانات."
    ),
    ErasureAlreadySignedError: "التوقيعُ مسجَّلٌ من قبل — ينتظر الطلبُ الموقّعَ الآخر.",
    ErasureNoteRequiredError: "سبب الرفض مطلوب.",
}


def failure_for(code: str) -> tuple[str, str]:
    """(الرمز، الجملة) لتعثّر المحو — والرمزُ المجهولُ `erasure_error`."""
    return ERASURE_FAILURES.get(code, ERASURE_FAILURES["erasure_error"])

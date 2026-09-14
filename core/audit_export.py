"""تدقيقُ التصدير — كلُّ وثيقةٍ تخرج من المنصّة تترك أثراً.

كان `action="export"` معرَّفاً في `AuditLog.ACTION_CHOICES` ولا يستدعيه أحد:
اثنان وثلاثون مصدِّراً بين PDF وExcel، وكشوفٌ فيها الرقمُ الشخصيُّ كاملاً،
ولا سطرَ يقول من أخرجها ومتى. وقانونُ حماية البيانات (13/2016) يطلب أثراً
لكلّ معالجةٍ تُخرج البياناتِ من حوزة المنصّة — وملفٌّ يُنزَّل هو ذاك.

فالقاعدةُ (`core/privacy.py`): وثيقةٌ فرديّةٌ تحمل الرقمَ كاملاً ثمنُها
تدقيق، والكشفُ الجماعيُّ يُستر ويُدقَّق كذلك. والحارسُ في
`tests/test_national_id_never_bulk.py` يرفض مصدِّراً لا يستدعي `log_export`.

ما يُكتب في السجلّ لا يحمل بياناتٍ شخصيّة: `object_repr` اسمُ الوثيقة أو
صاحبِها أو فصلِها، و`changes` نوعٌ وعددُ صفوفٍ ورايةُ «فيها رقمٌ كامل».
ولا يُكتب الرقمُ نفسُه ولا اسمُ ملفٍّ يحمله.
"""

from __future__ import annotations

from core.models.audit import AuditLog


def log_export(
    request,
    kind: str,
    *,
    rows: int | None = None,
    full_national_id: bool = False,
    object_id: str = "",
    object_repr: str = "",
) -> None:
    """يسجّل توليدَ وثيقةٍ أو ملفٍّ: من، وماذا، وكم صفّاً، وهل فيها رقمٌ كامل.

    `kind` معرّفٌ ثابتٌ للوثيقة (`reports.certificate`, `student_affairs.students_xlsx`)،
    و`rows` عددُ الأشخاص أو السطور فيها (`None` لوثيقةٍ بلا صفوف كلائحةٍ أو ملخّص)،
    و`full_national_id` صادقةٌ حين يحمل الملفُّ رقماً شخصيّاً غيرَ مستور.

    والفشلُ في الكتابة يُوقف التصدير: وثيقةٌ بلا أثرٍ أسوأُ من وثيقةٍ تأخّرت.
    """
    user = getattr(request, "user", None)
    if user is not None and not getattr(user, "is_authenticated", False):
        user = None
    AuditLog.log(
        user=user,
        action="export",
        model_name="other",
        object_id=object_id,
        object_repr=object_repr or kind,
        changes={
            "kind": kind,
            "rows": rows,
            "full_national_id": bool(full_national_id),
        },
        request=request,
    )

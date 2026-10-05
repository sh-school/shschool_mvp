"""إخفاءُ ما لا يحتاج القارئُ أن يراه كاملاً.

الرقمُ الشخصيُّ معرّفٌ حكوميٌّ دائمٌ لا يُبدَّل، وكشفُه بالجملة أثقلُ من كشفه
واحداً: صفحةٌ فيها خمسون رقماً تُصوَّر وتُرسَل، وواحدٌ يُفتح ملفُّه لا يُصوَّر.
وقانونُ حماية البيانات القطريّ (13/2016) يقوم على التقليل: لا يُعرض من البيان
إلّا ما تحتاجه المهمّةُ القائمة.

وحاجةُ من يقرأ كشفاً أن **يميّز** لا أن **يعرف**: أربعُ خاناتٍ أخيرةٌ تفصل
الطالبَ عن أخيه وتطابق ما في يد القارئ من ورق، ولا تُعيد بناءَ الرقم. والرقمُ
كاملاً يبقى في ملفّ صاحبه لمن فتحه بقصد.

والبحثُ يقع على الرقم الكامل لا على المُخفى: من كتب رقماً كاملاً وجد صاحبَه.

القاعدةُ المكتوبة (2026-09-14)
------------------------------

1. **كشفٌ جماعيّ ← مستورٌ دائماً.** قائمةٌ أو جدولٌ أو ردُّ بحثٍ JSON أو تقريرٌ
   يضمّ أكثرَ من شخص — على الشاشة أو في PDF — يعرض الرقمَ بـ`|mask_id`
   (في القوالب) أو `mask_national_id` (في بايثون). ولا فرقَ بين تقريرٍ
   يُطبع وتقريرٍ يُعرض: كشفُ حضورِ فصلٍ وشهاداتُ فصلٍ في ملفٍّ واحد كشوفٌ
   جماعيّة.

2. **وثيقةٌ فرديّةٌ رسميّةٌ تُسلَّم لصاحبها ← الرقمُ كاملاً، مع تدقيق.**
   شهادةٌ، أو كشفُ نتيجةِ طالبٍ، أو تعهّدٌ، أو إنذارٌ، أو ملفُّ طالبٍ PDF —
   رقمٌ مستورٌ فيها لا يُغني عن صاحبها. وثمنُ الكمال أثر: كلُّ توليدٍ يُسجَّل
   `AuditLog(action="export")` عبر `core.audit_export.log_export` بنوع
   الوثيقة وعدد صفوفها وهل فيها رقمٌ كامل.

3. **كلُّ مصدِّرٍ يُدقَّق**، كاملَ الرقم كان أو مستورَه: ملفُّ Excel أو PDF
   يخرج من المنصّة يترك سطراً في سجلّ التدقيق — من أخرجه ومتى ومن أين وكم صفّاً.

4. **الاستثناءُ المسمّى لا الضمنيّ**: الوثائقُ الفرديّةُ قائمةٌ باسمها في
   `tests/test_national_id_never_bulk.py`، وما ليس فيها يُستر.

والحارسُ الذي يحمي القاعدة: `tests/test_national_id_never_bulk.py`.
"""

from typing import Any

from django.db.models import Q

#: ما يُبقى ظاهراً من ذيل الرقم — يميّز ولا يُعرّف.
VISIBLE_TAIL = 4

#: من يبحث بجزءٍ من الرقم الشخصيّ (قرارُ المالك: الإدارةُ وحدَها). غيرُهم بالتساوي التامّ.
PARTIAL_ID_SEARCH_ROLES = frozenset({"principal", "vice_admin", "vice_academic"})


def may_search_id_partially(user: Any) -> bool:
    """أيجوز لهذا المستخدم أن يبحث بجزءٍ من الرقم الشخصيّ؟ — الإدارةُ والمشرفُ العامّ فقط.

    البحثُ الجزئيُّ مرشادٌ: كلُّ خانةٍ تُضيّق النتيجةَ والاسمُ يظهر، فيُستخرج رقمٌ لم يملكه
    السائلُ رقماً رقماً وإن سُتر في الجدول (#849). فلا يُفتح إلّا لمن يُدير سجلَّ الأشخاص.
    """
    if user is None or not getattr(user, "is_authenticated", False):
        return False
    if getattr(user, "is_superuser", False):
        return True
    return user.role in PARTIAL_ID_SEARCH_ROLES


def national_id_search_q(field: str, term: str, *, user: Any = None, partial: bool = False) -> Q:
    """شرطُ بحثٍ في الرقم الشخصيّ: تساوٍ تامٌّ، أو احتواءٌ لمن يجوز له.

    الاحتواءُ حين `partial` صريحاً (من يستدعي من غير عرض: مصدِّرٌ يعرف مستخدمَه)، أو حين `user`
    يجوز له (`may_search_id_partially`). `field` مسارُ الحقل كاملاً (`national_id` أو
    `user__national_id`…). والمدخلُ الفارغُ لا يطابق شيئاً.
    """
    text = (term or "").strip()
    lookup = f"{field}__icontains" if partial or may_search_id_partially(user) else field
    if not text:
        lookup, text = "pk__in", []  # type: ignore[assignment]
    return Q(**{lookup: text})


def mask_national_id(value: str | None, tail: int = VISIBLE_TAIL) -> str:
    """يُبقي آخرَ `tail` خاناتٍ ويستر ما قبلها.

    ورقمٌ أقصرُ من الذيل يُستر كلُّه: إظهارُ رقمٍ من خمس خاناتٍ بأربعٍ منه
    كشفٌ لا ستر.
    """
    text = (value or "").strip()
    if not text:
        return ""
    if len(text) <= tail + 1:
        return "*" * len(text)
    return f"{'*' * (len(text) - tail)}{text[-tail:]}"


def mask_phone(value: str | None, tail: int = VISIBLE_TAIL) -> str:
    """يستر الجوّالَ إلّا ذيلَه — للسجلّات الدائمة التي يُراد منها المساءلةُ لا المعرفة.

    القاعدةُ نفسُها في `mask_national_id`: القارئُ يحتاج أن يميّز «تغيّر من ...1234 إلى ...5678» لا أن يعرف الرقم.
    """
    return mask_national_id(value, tail)


def mask_email(value: str | None) -> str:
    """يستر اسمَ البريد ويُبقي أوّلَ حرفٍ ونطاقَه: `a***@school.edu.qa`. وما ليس بريداً يُستر كلُّه."""
    text = (value or "").strip()
    if not text:
        return ""
    local, sep, domain = text.partition("@")
    if not sep or not local or not domain:
        return "*" * len(text)
    return f"{local[0]}***@{domain}"

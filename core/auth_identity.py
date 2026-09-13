"""core/auth_identity.py — معرّفُ الدخول: من يكتبه، وبأيّ مفتاحٍ يُقفل عليه.

الرقمُ الشخصيُّ القطريُّ بياناتٌ شخصيّةٌ بنصّ PDPPL، ونحن نشفّره في القاعدة
(`national_id_encrypted` + HMAC) ثمّ كنّا **نطلب من الموظّف كتابتَه في نموذج
الدخول كلَّ صباح** — فيمرّ في الشبكة، ويسكن في `axes_accessattempt` نصّاً
صريحاً، ويُقرأ من خلف الكتف. فصار الكادرُ يدخل برقمه الوظيفيّ: معرّفٌ إداريٌّ
لا يكشف هويّةً مدنيّة.

و`USERNAME_FIELD` لا يُبدَّل — حقلٌ واحدٌ للنموذج كلِّه، و1435 حساب طالبٍ ووليِّ
أمرٍ لا رقمَ وظيفيَّ لهم. فيبقى الحقلُ كما هو، ويتغيّر **ما يقبله البابُ وما
يُقفل عليه**.

## مفتاحُ القفل — أخطرُ ما في هذا الملفّ

في المنصّة ثلاثةُ أقفال: حدُّ العنوان (`ratelimit`)، وaxes، وعدّادٌ خاصٌّ على
`CustomUser`. ومفتاحُ الأخيرَين كان **النصَّ المكتوب** لا المستخدمَ نفسَه. ولو
قُبل معرّفان بلا تطبيعٍ لصار للموظّف الواحد مفتاحا قفلٍ اثنان — أي عشرُ
محاولاتٍ لا خمس، في الآليّتين معاً.

فيُحَلّ المعرّفُ إلى مستخدمٍ أوّلاً، ويُسلَّم إلى القفلين **مفتاحٌ معياريٌّ
واحد**: معرّفُ المستخدم إن عُرف، وبصمةٌ غيرُ عكوسةٍ للنصّ إن لم يُعرف. وبهذا
لا يصل رقمٌ شخصيٌّ إلى سجلّ المحاولات أصلاً — لا للكادر ولا للطلبة.
"""

from __future__ import annotations

import hashlib

from django.conf import settings

#: يُخزَّن على الطلب فلا يُستعلَم مرّتين في الطلب الواحد (الباب ينادي، وaxes ينادي).
_CACHE_ATTR = "_auth_identity_cache"

EMPLOYEE_NUMBER = "employee_number"
NATIONAL_ID = "national_id"
UNKNOWN = "unknown"


def resolve_user(identifier: str, request=None):
    """صاحبُ هذا المعرّف، أو `None`.

    الترتيبُ مقصود: الرقمُ الوظيفيُّ أوّلاً لأنّه مفهرسٌ وفريدٌ جزئيّاً (الفراغُ
    مستثنى بالقيد `unique_employee_number`)، ثمّ الرقمُ الشخصيُّ عبر HMAC، ثمّ
    نصّاً صريحاً للحسابات التي لم تُشفَّر بعد.

    ولا نميّز بطول الرقم: الأرقامُ الوظيفيّةُ اليومَ خمسُ خاناتٍ أو ستّ
    والشخصيّةُ إحدى عشرة، والتقاطعُ صفر — لكنّ هذا مصادفةُ بياناتٍ لا ضمانُ
    بنية. ووزارةٌ تُصدر يوماً رقماً وظيفيّاً من إحدى عشرة خانةً تُسقط النظامَ
    صامتاً.
    """
    raw = (identifier or "").strip()
    if not raw:
        return None

    cache = getattr(request, _CACHE_ATTR, None) if request is not None else None
    if cache is not None and raw in cache:
        return cache[raw]

    user = _lookup(raw)

    if request is not None:
        if cache is None:
            cache = {}
            setattr(request, _CACHE_ATTR, cache)
        cache[raw] = user
    return user


def _lookup(raw: str):
    from core.models import CustomUser
    from core.models._crypto import hmac_field

    user = CustomUser.objects.filter(employee_number=raw).first()
    if user is not None:
        return user

    hashed = hmac_field(raw)
    if hashed and hashed != raw:
        user = CustomUser.objects.filter(national_id_hmac=hashed).first()
        if user is not None:
            return user

    return CustomUser.objects.filter(national_id=raw).first()


def identifier_kind(user, identifier: str) -> str:
    """أيَّ معرّفٍ استعمل هذا الداخل — لتُقاس نهايةُ النافذة المزدوجة بالعدّ.

    فالقطعُ يقع حين يبلغ استعمالُ الرقم الشخصيّ من أصحاب الأرقام الوظيفيّة
    صفراً، لا في تاريخٍ يُختار على الورق.
    """
    raw = (identifier or "").strip()
    if user is None or not raw:
        return UNKNOWN
    if user.employee_number and raw == user.employee_number:
        return EMPLOYEE_NUMBER
    return NATIONAL_ID


def lockout_key(identifier: str, request=None) -> str:
    """المفتاحُ المعياريُّ الذي يُقفل عليه — بلا بياناتٍ شخصيّة.

    مستخدمٌ معروفٌ = معرّفُه، فمهما بدّل بين معرّفَيه بقي مفتاحُه واحداً. ومجهولٌ
    = بصمةٌ غيرُ عكوسةٍ للنصّ، فالقفلُ يعمل على من يجرّب أرقاماً عشوائيّةً ولا
    يُخزَّن ما جرّبه.
    """
    raw = (identifier or "").strip()
    if not raw:
        return "x:empty"
    user = resolve_user(raw, request)
    if user is not None:
        return f"u:{user.pk}"
    digest = hashlib.sha256(f"{settings.SECRET_KEY}:{raw}".encode()).hexdigest()
    return f"x:{digest[:32]}"


def axes_username(request, credentials=None) -> str:
    """ما يقفل عليه django-axes — يُضبط بـ`AXES_USERNAME_CALLABLE`.

    وبلا هذا يقرأ axes حقلَ النموذج خاماً، فيكتب الرقمَ الشخصيَّ نصّاً صريحاً
    في `axes_accessattempt` لكلّ محاولةٍ فاشلة.
    """
    raw = ""
    if credentials:
        for key in ("identifier", "username", "national_id"):
            if credentials.get(key):
                raw = credentials[key]
                break
    if not raw and request is not None:
        post = getattr(request, "POST", None)
        if post:
            raw = post.get("identifier") or post.get("national_id") or ""
    return lockout_key(raw, request)

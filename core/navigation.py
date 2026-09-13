"""هل يفتح هذا المستخدمُ هذه الشاشة؟ — يسأل الحارسَ نفسَه لا قائمةً موازية.

كانت القائمةُ الجانبيّةُ تُبنى من فروعٍ على اسم الدور (``{% if role == "teacher" %}``)،
والحارسُ على الشاشة يُبنى من مجموعةٍ أخرى. فتَعِد القائمةُ بما يردّه الحارس: وجد اختبارُ
``test_sidebar_links_are_reachable`` روابطَ كثيرةً تُعرض ثمّ تُرفض بـ403، وأُصلحت واحداً
واحداً — والفئةُ نفسُها باقية ما دام للقائمة مصدرٌ وللحارس مصدر.

فهذه الدالّةُ تجعل المصدرَ واحداً: تحلّ اسمَ الرابط إلى الشاشة، وتقرأ بوّابةَ الوحدة كما
يقرؤها الوسيط، ثمّ أدوارَ الحارس كما يفحصها ``capability_required``. والرابطُ الذي لا يُفتح
لا يُعرض. وفروعُ الأدوار تبقى لترتيب القائمة وتجميعها — لا لتقرير ما يُفتح.

وما لا يُعرف من خارج الشاشة — فحصُ القدرة داخلَها أو ملكيّةُ الكائن — يُعدّ مفتوحاً هنا،
وتقرّره الشاشةُ نفسُها؛ وتلك مسمّاةٌ في ``tests/test_every_route_is_guarded.py``.
"""

from functools import lru_cache

from django.urls import NoReverseMatch, resolve, reverse


def _guard_roles(view):
    fn, seen = view, set()
    while fn is not None and id(fn) not in seen:
        seen.add(id(fn))
        roles = getattr(fn, "_required_roles", None)
        if roles is not None:
            return frozenset(roles)
        fn = getattr(fn, "__wrapped__", None)
    return None


@lru_cache(maxsize=4096)
def _role_opens(role: str, url_name: str) -> bool:
    """الجوابُ لدورٍ ورابط — ثابتٌ ما دامت الشيفرةُ واحدة، فيُحفظ للعمليّة."""
    from core.middleware import EXEMPT
    from core.module_registry import get_protected_paths

    try:
        path = reverse(url_name)
    except NoReverseMatch:
        return False
    if not any(path.startswith(e) for e in EXEMPT):
        for prefix, allowed in get_protected_paths().items():
            if path.startswith(prefix):
                if role not in allowed:
                    return False
                break
    roles = _guard_roles(resolve(path).func)
    return roles is None or role in roles


def can_open(user, url_name: str) -> bool:
    """هل يُفتح الرابطُ ``url_name`` (بلا وسائط) لهذا المستخدم؟"""
    if user is None or not getattr(user, "is_authenticated", False):
        return False
    if user.is_superuser:
        return True
    return _role_opens(user.get_role() or "", url_name)

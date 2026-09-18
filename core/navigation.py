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

from collections.abc import Callable
from functools import lru_cache
from typing import Any

from django.urls import NoReverseMatch, resolve, reverse


def _guard_roles(view: Any) -> frozenset[str] | None:
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


def _guard_grant(view: Any) -> Callable[[Any], bool] | None:
    fn, seen = view, set()
    while fn is not None and id(fn) not in seen:
        seen.add(id(fn))
        grant: Callable[[Any], bool] | None = getattr(fn, "_grant", None)
        if grant is not None:
            return grant
        fn = getattr(fn, "__wrapped__", None)
    return None


@lru_cache(maxsize=1024)
def _url_grant(
    url_name: str,
) -> tuple[Callable[[Any], bool] | None, frozenset[str] | None]:
    """منحُ الحارس لهذا الرابط وأدوارُ بوّابة وحدته — ``(grant, gate)``.

    المنحُ لا يقرؤه الدور (بديلُ الجناح بتكليفه)، والبوّابةُ تسبق الحارس: فمن لا تُدخله
    بوّابةُ الوحدة بدوره لا يبلغه المنح، ولا يَعِده الرابط.
    """
    from core.middleware import EXEMPT
    from core.module_registry import get_protected_paths

    try:
        path = reverse(url_name)
    except NoReverseMatch:
        return None, None
    gate = None
    if not any(path.startswith(e) for e in EXEMPT):
        for prefix, allowed in get_protected_paths().items():
            if path.startswith(prefix):
                gate = frozenset(allowed)
                break
    return _guard_grant(resolve(path).func), gate


def can_open(user: Any, url_name: str) -> bool:
    """هل يُفتح الرابطُ ``url_name`` (بلا وسائط) لهذا المستخدم؟"""
    if user is None or not getattr(user, "is_authenticated", False):
        return False
    if user.is_superuser:
        return True
    role = user.get_role() or ""
    if _role_opens(role, url_name):
        return True
    grant, gate = _url_grant(url_name)
    if gate is not None and role not in gate:
        # بوّابةٌ تردّه بدوره قد تُدخله بمنحها (معلّمٌ هو وليُّ أمرٍ في ``/parents/``)،
        # ثمّ يقرّر حارسُ الشاشة نفسُه: بدوره، أو بمنحه، أو لا حارسَ فتقرّر الشاشة.
        module_grant = _module_grant_for(url_name)
        if module_grant is None or not module_grant(user):
            return False
        if _guard_admits_role(role, url_name):
            return True
    if grant is None:
        return False
    return bool(grant(user))


@lru_cache(maxsize=1024)
def _module_grant_for(url_name: str) -> Callable[[Any], bool] | None:
    """منحُ بوّابة الوحدة التي يقع تحتها الرابط — أو ``None``."""
    from core.middleware import EXEMPT
    from core.module_registry import get_protected_grants, get_protected_paths

    try:
        path = reverse(url_name)
    except NoReverseMatch:
        return None
    if any(path.startswith(e) for e in EXEMPT):
        return None
    for prefix in get_protected_paths():
        if path.startswith(prefix):
            return get_protected_grants().get(prefix)
    return None


@lru_cache(maxsize=4096)
def _guard_admits_role(role: str, url_name: str) -> bool:
    """حارسُ الشاشة وحدَه (بلا بوّابة الوحدة) — أيُدخل هذا الدور؟ ولا حارسَ يعني نعم."""
    roles = _guard_roles(resolve(reverse(url_name)).func)
    return roles is None or role in roles

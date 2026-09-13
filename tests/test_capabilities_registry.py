"""سجلُّ القدرات يصف المنصّةَ كما هي — لا أوسعَ منها ولا أضيق.

الخطوةُ الأولى من طبقة القدرات (ت٣) سجلٌّ يُعرض قبل تحويل أيّ حارس. فإن نقص منه حارسٌ قائم
عُرض على المستخدم ما ليس في المنصّة، وإن اختُرع فيه عضوٌ صار القرارُ مبنيّاً على وهم. وهذا
الملفُّ يثبّت الأمرين: كلُّ حارسٍ في المنصّة يطابق قدرةً في السجلّ بأعضائه بعد الوراثة.
"""

import pytest
from django.urls import URLPattern, URLResolver, get_resolver

from core.capabilities import capability, capability_required, has_capability, registry
from core.models.access import Role
from tests.conftest import MembershipFactory, RoleFactory, UserFactory

ROLE_NAMES = {name for name, _ in Role.ROLES}


def _walk(patterns):
    for p in patterns:
        if isinstance(p, URLResolver):
            yield from _walk(p.url_patterns)
        elif isinstance(p, URLPattern):
            yield p.callback


def _guard_roles(callback):
    fn, seen = callback, set()
    while fn is not None and id(fn) not in seen:
        seen.add(id(fn))
        roles = getattr(fn, "_required_roles", None)
        if roles is not None:
            return frozenset(roles)
        fn = getattr(fn, "__wrapped__", None)
    return None


def test_every_guard_in_the_platform_matches_a_capability():
    known = {cap.expanded_roles for cap in registry().values()}
    unmatched = {}
    for callback in _walk(get_resolver().url_patterns):
        roles = _guard_roles(callback)
        if roles is not None and roles not in known:
            name = f"{callback.__module__}.{getattr(callback, '__qualname__', '')}"
            unmatched[name] = sorted(roles)

    assert not unmatched, "حارسٌ لا قدرةَ تطابقه في core/capabilities.py:\n  " + "\n  ".join(
        f"{k}: {v}" for k, v in sorted(unmatched.items())
    )


def test_the_sweep_sees_the_guards():
    guarded = [cb for cb in _walk(get_resolver().url_patterns) if _guard_roles(cb) is not None]

    assert len(guarded) > 200, len(guarded)


@pytest.mark.parametrize("key", sorted(registry()))
def test_every_capability_names_real_roles_and_says_what_it_is(key):
    cap = capability(key)

    assert cap.roles, "قدرةٌ بلا أدوار"
    assert cap.roles <= ROLE_NAMES, sorted(cap.roles - ROLE_NAMES)
    assert cap.label and cap.basis and cap.scope


def test_an_unknown_capability_fails_loudly():
    with pytest.raises(KeyError, match="لا قدرةَ"):
        capability_required("assessments.enter_grade")  # ينقصها حرف


@pytest.mark.django_db
def test_has_capability_follows_inheritance_like_the_guard(school):
    """منسّقُ الأنشطة يرث المنسّق — فيملك ما يملكه دون أن يُكتب في القدرة."""
    coordinator = UserFactory()
    MembershipFactory(
        user=coordinator,
        school=school,
        role=RoleFactory(school=school, name="activities_coordinator"),
    )
    student = UserFactory()
    MembershipFactory(user=student, school=school, role=RoleFactory(school=school, name="student"))

    assert "activities_coordinator" not in capability("attendance.mark").roles
    assert has_capability(coordinator, "attendance.mark")
    assert not has_capability(student, "assessments.enter_grades")


def test_the_decorator_carries_the_capability_and_the_same_roles():
    @capability_required("quality.manage")
    def view(request):
        return None

    assert view._capability == "quality.manage"
    assert frozenset(view._required_roles) == capability("quality.manage").expanded_roles


def _capability_of(callback):
    fn, seen = callback, set()
    while fn is not None and id(fn) not in seen:
        seen.add(id(fn))
        if getattr(fn, "_capability", None):
            return fn._capability
        fn = getattr(fn, "__wrapped__", None)
    return None


def test_every_guarded_route_names_its_capability():
    """الحارسُ يسمّي قدرتَه — لا قائمةَ أدوارٍ حرفيّةً تعود من الباب الخلفيّ.

    حُوِّلت الحرّاسُ كلُّها إلى ``capability_required`` بعد أن ثبت بلقطةٍ قبل التحويل وبعده
    أنّ 903 مساراتٍ لم يتغيّر عضوٌ في أدوارها. فحارسٌ جديدٌ بـ``role_required`` مباشرةً
    يُسقط هذا الاختبار: يُضاف إلى السجلّ باسمه، أو يُستعمل ما فيه.
    """
    bare = []
    for callback in _walk(get_resolver().url_patterns):
        if _guard_roles(callback) is not None and _capability_of(callback) is None:
            bare.append(f"{callback.__module__}.{getattr(callback, '__qualname__', '')}")

    assert not bare, "حارسٌ بلا قدرةٍ مسمّاة:\n  " + "\n  ".join(sorted(bare))

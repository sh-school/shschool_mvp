"""[SECURITY] لا مسارَ في المنصّة بلا حراسةٍ على الدور — إلّا ما استُثني باسمه وسببه.

الوسيطُ يفرض تسجيلَ الدخول على كلّ مسار، وهذا صحيح. لكنّ «مسجَّلَ الدخول» ليس صلاحيّة:
مراجعةُ 2026-09-13 وجدت خمسةَ مواضع تكتفي به، فبلغ الطالبُ سجلَّ حضور المدرسة ودرجاتِ
زملائه وأسماءَ الكادر (أُصلحت في #222 و#223). وكلُّها من فئةٍ واحدة: شاشةٌ أو نقطةُ API
نُسي حارسُها، ولا بوّابةَ وحدةٍ فوقها تلتقط النسيان.

فهذا الحارسُ يمشي كلَّ مسارٍ من ``get_resolver()`` ويطلب لكلٍّ واحداً من:

- **بوّابةَ وحدة** في ``module_registry`` تطابق بادئتَه (كما يطابقها الوسيط)؛
- **أو حارسَ دورٍ** على الدالّة (``_required_roles`` من ``role_required``/``department_scoped``)؛
- **أو صلاحيّةَ DRF** غيرَ «مسجَّل الدخول» و«الجميع»؛
- **أو استثناءً مسمّى** في ``GUARDED_INSIDE`` أو ``OPEN_BY_DESIGN`` بسببه.

والاستثناءُ ليس ثغرة: شاشةُ الإسناد تفحص القدرةَ ونطاقَ القسم داخلَها، والإشعاراتُ بياناتُ
صاحبها وحدَه. لكنّه يُكتب هنا، فيراه المراجعُ ويسأل عنه — لا يمرّ صامتاً كما مرّت الخمسة.
"""

import re

from django.urls import URLPattern, URLResolver, get_resolver

from core.middleware import EXEMPT
from core.module_registry import get_protected_paths

#: صلاحيّاتُ DRF التي لا تقول شيئاً عن الدور.
_NOT_A_ROLE_CHECK = {"IsAuthenticated", "AllowAny"}

#: يفحص الصلاحيّةَ داخلَه — القدرةَ أو الكائنَ أو صاحبَ البيانات. المسارُ ← أين يُفحص.
GUARDED_INSIDE = {
    "academic/assignments/": "_guard() — قدرةُ الإدخال/المراجعة/الاعتماد، ونطاقُ قسم المنسّق",
    "academic/assignments/subjects/": "_guard() — قدرةُ الإدخال/المراجعة/الاعتماد، ونطاقُ قسم المنسّق",
    "academic/assignments/<uuid:teacher_id>/add/": "_guard() — قدرةُ الإدخال/المراجعة/الاعتماد، ونطاقُ قسم المنسّق",
    "academic/assignments/<uuid:teacher_id>/load/": "_guard() — قدرةُ الإدخال/المراجعة/الاعتماد، ونطاقُ قسم المنسّق",
    "academic/assignments/<uuid:teacher_id>/cancel-transfer/": "_guard() — قدرةُ الإدخال/المراجعة/الاعتماد، ونطاقُ قسم المنسّق",
    "academic/assignments/<uuid:teacher_id>/department/": "_guard() — قدرةُ الإدخال/المراجعة/الاعتماد، ونطاقُ قسم المنسّق",
    "academic/assignments/<uuid:teacher_id>/preparation/": "_guard() — قدرةُ الإدخال/المراجعة/الاعتماد، ونطاقُ قسم المنسّق",
    "academic/assignments/<uuid:teacher_id>/<slug:action>/": "_guard() — قدرةُ الإدخال/المراجعة/الاعتماد، ونطاقُ قسم المنسّق",
    "academic/assignments/row/<uuid:assignment_id>/periods/": "_guard() — قدرةُ الإدخال/المراجعة/الاعتماد، ونطاقُ قسم المنسّق",
    "academic/assignments/row/<uuid:assignment_id>/double/": "_guard() — قدرةُ الإدخال/المراجعة/الاعتماد، ونطاقُ قسم المنسّق",
    "academic/assignments/row/<uuid:assignment_id>/parallel/": "_guard() — قدرةُ الإدخال/المراجعة/الاعتماد، ونطاقُ قسم المنسّق",
    "academic/assignments/row/<uuid:assignment_id>/remove/": "_guard() — قدرةُ الإدخال/المراجعة/الاعتماد، ونطاقُ قسم المنسّق",
    "dbmedia/<path:name>": "_authorize() — مالكُ الملفّ أو الدورُ المسجَّل له، وإلّا 404 (fail-closed)",
    "search/": "الطلبةُ للكادر، والرقمُ الشخصيُّ لشؤون الطلبة، والكادرُ للمدير (#222)",
    "developer-feedback/inbox/": "DeveloperOnlyMixin",
    "developer-feedback/inbox/<int:pk>/": "DeveloperOnlyMixin",
    "developer-feedback/onboarding/": "NotStudentMixin — ورسائلُ المستخدم لنفسه",
    "developer-feedback/send/": "OnboardingRequiredMixin — يكتب رسالتَه هو",
    "developer-feedback/success/": "NotStudentMixin — صفحةُ تأكيدٍ بلا بيانات",
    "developer-feedback/my-messages/": "الاستعلامُ filter(user=request.user)",
    "developer-feedback/my-messages/<int:pk>/edit/": "الاستعلامُ filter(user=request.user)",
    "api/v1/erasure/request/": "وليُّ الأمر لأبنائه وحدَهم، أو المدير — وإلّا 403",
    "api/v1/erasure/requests/<uuid:request_id>/": "مقدِّمُ الطلب أو المدير — وإلّا 403",
    "api/v1/library/borrowings/": "المدرسةُ لـLIBRARY_BORROWINGS_ALL، ولغيرهم استعاراتُهم وأبنائهم (#223)",
    "api/v1/me/": "بياناتُ المستخدم نفسِه",
    "api/v1/notifications/": "filter(user=request.user)",
    "api/v1/notifications/<uuid:notif_id>/read/": "get_object_or_404(..., user=request.user)",
    "api/v1/notifications/mark-all-read/": "filter(user=request.user)",
    "api/v1/notification-preferences/": "تفضيلاتُ المستخدم نفسِه",
}

#: مفتوحٌ لكلّ مسجَّلٍ بقصد — المسارُ ← لماذا لا يكشف بياناتِ غيره.
OPEN_BY_DESIGN = {
    "": "تحويلٌ إلى لوحة التحكّم",
    "status/": "حالةُ الخدمة (القاعدة والذاكرة المؤقّتة) — بلا بياناتِ أشخاص",
    "styleguide/": "تحويلٌ دائمٌ (301) إلى دليل الهويّة — لا يعرض شيئاً",
    "styleguide/icons/": "مرجعُ الأيقونات — أسماءُ sprite.html بلا بيانات",
    "styleguide/components/": "دليلُ الهويّة: المكوّناتُ ولوحةُ الرموز — أمثلةٌ توضيحيّة بلا بيانات",
    "academic/evaluations/": "_stub_view — صفحةٌ قيد الإنشاء بلا بيانات",
    "academic/departments/": "_stub_view — صفحةٌ قيد الإنشاء بلا بيانات",
    "academic/test-analytics/": "_stub_view — صفحةٌ قيد الإنشاء بلا بيانات",
    "academic/department-reports/": "_stub_view — صفحةٌ قيد الإنشاء بلا بيانات",
    "academic/e-learning/": "_stub_view — صفحةٌ قيد الإنشاء بلا بيانات",
    "academic/class-performance/": "_stub_view — صفحةٌ قيد الإنشاء بلا بيانات",
    "academic/underperformance/": "_stub_view — صفحةٌ قيد الإنشاء بلا بيانات",
    "api/v1/library/books/": "فهرسُ الكتب — لا بياناتِ أشخاص",
    "api/v1/auth/token/": "إصدارُ رمز JWT — بابُ الدخول نفسُه",
    "api/v1/auth/token/refresh/": "تجديدُ رمز JWT",
    "api/v1/schema/": "مخطّطُ الـAPI — والوسيطُ يفرض الدخولَ على /api/",
    "api/v1/docs/": "توثيقُ الـAPI",
    "api/v1/redoc/": "توثيقُ الـAPI",
}


def _walk(patterns, prefix=""):
    for p in patterns:
        if isinstance(p, URLResolver):
            yield from _walk(p.url_patterns, prefix + str(p.pattern))
        elif isinstance(p, URLPattern):
            yield prefix + str(p.pattern), p.callback


def _sample(route):
    path = re.sub(r"<[^>]+>", "x", route.lstrip("^").rstrip("$")).replace("\\", "")
    return "/" + path


def _has_role_guard(callback):
    seen = set()
    fn = callback
    while fn is not None and id(fn) not in seen:
        seen.add(id(fn))
        if getattr(fn, "_required_roles", None) is not None:
            return True
        fn = getattr(fn, "__wrapped__", None)
    return False


def _drf_role_check(callback):
    cls = getattr(callback, "cls", None) or getattr(callback, "view_class", None)
    perms = getattr(cls, "permission_classes", None)
    if perms is None:
        return None
    names = {getattr(p, "__name__", str(p)) for p in perms}
    return bool(names - _NOT_A_ROLE_CHECK)


def _unguarded():
    gates = get_protected_paths()
    found = {}
    for route, callback in _walk(get_resolver().url_patterns):
        path = _sample(route)
        if any(path.startswith(e) for e in EXEMPT):
            continue
        if any(path.startswith(prefix) for prefix in gates):
            continue
        drf = _drf_role_check(callback)
        if drf is True or (drf is None and _has_role_guard(callback)):
            continue
        found[route] = f"{callback.__module__}.{getattr(callback, '__qualname__', callback)}"
    return found


def test_every_route_has_a_gate_a_guard_or_a_named_reason():
    named = GUARDED_INSIDE.keys() | OPEN_BY_DESIGN.keys()
    offenders = {r: v for r, v in _unguarded().items() if r not in named}

    assert not offenders, (
        f"{len(offenders)} مساراً يكتفي بتسجيل الدخول — أضف حارسَ دور، أو سمِّه هنا بسببه:\n  "
        + "\n  ".join(f"{r}  ←  {v}" for r, v in sorted(offenders.items()))
    )


def test_every_named_exception_still_exists():
    """استثناءٌ زال مسارُه يُحذف — وإلّا صار بابَ مرورٍ لمسارٍ جديدٍ بالاسم نفسه."""
    live = {route for route, _ in _walk(get_resolver().url_patterns)}
    stale = (GUARDED_INSIDE.keys() | OPEN_BY_DESIGN.keys()) - live

    assert not stale, sorted(stale)


def test_the_sweep_actually_finds_routes():
    """مسحٌ لا يرى شيئاً ينجح كاذباً."""
    routes = list(_walk(get_resolver().url_patterns))

    assert len(routes) > 300, len(routes)

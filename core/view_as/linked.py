"""الحسابُ المرتبط — تبديلُ هويّةٍ من حساب المطوّر إلى حسابه الآخر (معلّماً) والعودةُ منه (D-305م وD-306م).

شروطُ 0104 كلُّها هنا:

- **الهدف**: كادرٌ غيرُ مرتفعٍ في مدرسة المطوّر نفسِها — لا superuser ولا `is_staff` ولا مطوّرٌ ولا قيادةٌ عليا، ولا
  طالبٌ ولا وليُّ أمر — ولا ربطَ سلسليّاً (هدفٌ هو مطوّرٌ في ربطٍ آخر، أو مطوّرٌ هو هدفٌ في ربطٍ آخر).
- **التأكيد**: أوّلُ تبديلٍ في الجلسة يعيد تأكيدَ هويّة المطوّر نفسِه — رمزُ عامله الثاني إن فعّله، وإلّا كلمةُ مروره —
  لا كلمةَ المعلّم. وربطٌ لم يُؤكَّد قطّ يُؤكَّد بها أيضاً. وقفلُ المحاولات الخاطئة وحجزُ الرمز المستعمَل في ذاكرةٍ
  تشترك فيها العمليّات (Redis في الإنتاج)، فإن لم تكن أو تعذّرت أُقفل التأكيدُ ولم يُفتح بلا عدّ.
- **الجلسة**: لا `login()` عاديّ؛ يُدوَّر مفتاحُ الجلسة ورمزُ CSRF دخولاً وخروجاً، ويُخزَّن المطوّرُ الفعليّ في علامةٍ
  موقَّعةٍ مع بصمة كلمة مروره، فتغييرُها يُسقط الانتحالَ كلَّه. 15 دقيقةً خاملةً وسقفُ ساعةٍ و10 تبديلاتٍ في الساعة.
- **الخروج يعيد المطوّرَ لا يُخرجه** — إلّا إن لم يعد مطوّراً فاعلاً أو تغيّرت كلمةُ مروره: عندها تُغلق الجلسةُ كلُّها.
"""

from __future__ import annotations

import logging
from typing import Any

from django.conf import settings
from django.contrib.auth import BACKEND_SESSION_KEY, HASH_SESSION_KEY, SESSION_KEY, logout
from django.core.cache import cache
from django.middleware.csrf import rotate_token
from django.utils import timezone

from core.models.access import LEADERSHIP, TIER_3_SUPERVISORS, TIER_4_STAFF
from core.unrestricted_role import has_unrestricted_role

from . import state
from .policy import (
    LINKED_CAP_SECONDS,
    LINKED_IDLE_SECONDS,
    REAUTH_FAILURES,
    REAUTH_LOCK_SECONDS,
    TOTP_REPLAY_SECONDS,
)

logger = logging.getLogger(__name__)

#: أدوارُ الكادر التي يجوز أن يكون الحسابُ المرتبطُ عليها: ما دون القيادة العليا (الإدارةُ العليا هدفٌ مرتفع).
TARGET_ROLES = frozenset(TIER_3_SUPERVISORS | TIER_4_STAFF) - LEADERSHIP

#: ذاكراتٌ لا تشترك فيها العمليّات: قفلٌ فيها يُعدّ لكلّ عاملٍ وحدَه، فتصير خمسُ المحاولات خمساً لكلّ عامل.
_PROCESS_LOCAL_CACHES = frozenset(
    {
        "django.core.cache.backends.locmem.LocMemCache",
        "django.core.cache.backends.dummy.DummyCache",
    }
)


def link_problems(developer: Any, target: Any, *, exclude_pk: Any = None) -> list[str]:
    """أسبابُ رفض الربط (أو التبديل عبره) — قائمةٌ فارغةٌ إن صحّ."""
    from core.developer_access import is_platform_developer
    from core.models import LinkedAccount

    problems: list[str] = []
    if developer.pk == target.pk:
        return ["لا يُربط الحسابُ بنفسه."]
    if not (developer.is_active and has_unrestricted_role(developer)):
        problems.append("صاحبُ الربط ليس مطوّرَ المنصّة الفاعل.")
    if not target.is_active:
        problems.append("الحسابُ المرتبط معطَّل.")
    if target.is_superuser or target.is_staff or is_platform_developer(target):
        problems.append("الحسابُ المرتبط مرتفعُ الصلاحيّة (مشرفٌ أعلى أو موظّفُ إدارةٍ تقنيّة أو مطوّر).")
    if target.get_role() not in TARGET_ROLES:
        problems.append(
            "الحسابُ المرتبط يجب أن يكون من الكادر دون القيادة العليا — لا طالباً ولا وليَّ أمر."
        )
    if developer.get_school() is None or developer.get_school() != target.get_school():
        problems.append("الحسابُ المرتبط من مدرسةٍ غير مدرسة المطوّر.")
    others = (
        LinkedAccount.objects.exclude(pk=exclude_pk) if exclude_pk else LinkedAccount.objects.all()
    )
    if others.filter(developer=target).exists() or others.filter(target=developer).exists():
        problems.append("لا ربطَ سلسليّاً: أحدُ الطرفين طرفٌ في ربطٍ آخر بالاتّجاه المعاكس.")
    return problems


def entry_problems(request: Any, target: Any) -> list[str]:
    """ما يمنع الدخولَ الآن وإن صحّ الربط: حسابٌ لا يبلغ صفحةً بلا ما يُحجب أثناء الانتحال."""
    from core.mfa_session import MFA_SESSION_KEY, needs_second_factor
    from core.middleware import TwoFactorEnforcementMiddleware

    problems: list[str] = []
    if not lock_store_shared():
        problems.append(
            "قفلُ التأكيد يحتاج ذاكرةً مشتركةً (Redis) وهذه البيئةُ بلا واحدة — الحسابُ المرتبطُ موقوفٌ فيها."
        )
    if target.must_change_password:
        problems.append("على الحساب المرتبط تغييرُ كلمة مروره — ادخله بنفسك مرّةً لذلك.")
    if TwoFactorEnforcementMiddleware._must_set_up(target):
        problems.append("الحسابُ المرتبط لم يفعّل المصادقةَ الثنائيّة — فعّلها له بدخوله بنفسك.")
    if needs_second_factor(target) and not request.session.get(MFA_SESSION_KEY):
        problems.append(
            "الحسابُ المرتبط يطلب رمزاً ثنائيّاً وجلستُك بلا رمز — فعّل الثنائيّة لحسابك أوّلاً."
        )
    return problems


# ── إعادةُ التأكيد ───────────────────────────────────────────────


def has_reauth(request: Any, actor: Any) -> bool:
    payload = state.unsign(request.session.get(state.REAUTH_KEY), state.REAUTH_SALT)
    return bool(
        payload
        and payload.get("a") == str(actor.pk)
        and payload.get("h") == actor.get_session_auth_hash()
    )


def uses_second_factor(actor: Any) -> bool:
    from core.views_auth import usable_totp_secret

    return bool(actor.totp_enabled and usable_totp_secret(actor))


def lock_store_shared() -> bool:
    """قفلُ التأكيد وحجزُ الرمز في ذاكرةٍ تشترك فيها العمليّات — شرطُ 0104 قبل النشر.

    الإنتاجُ يأخذ Redis من `REDIS_URL` وإلّا ذاكرةَ العمليّة (`settings/production.py`)، فبلا Redis يُوقف الحسابُ
    المرتبطُ ولا يعمل بقفلٍ مقسومٍ على العمّال. والتطويرُ عمليّةٌ واحدة (DEBUG) فلا يلزمه.
    """
    backend = settings.CACHES.get("default", {}).get("BACKEND", "")
    return settings.DEBUG or backend not in _PROCESS_LOCAL_CACHES


#: المفتاحُ نفسُه في `core/views_auth.py` (VULN-001): فرمزٌ دخل به المطوّرُ لا يؤكّد هنا، ورمزٌ أكّد هنا لا يُدخل.
def _totp_used_key(actor: Any, code: str) -> str:
    return f"totp_used:{actor.id}:{code}"


def verify_reauth(actor: Any, secret: str) -> bool:
    """رمزُ عامله الثاني إن فعّله، وإلّا كلمةُ مروره — هويّةُ المطوّر لا المعلّم.

    والرمزُ الصحيحُ يُحجز بـ`cache.add` (ذرّيٌّ في Redis): طلبان متزامنان بالرمز نفسِه يصحّ أحدُهما فقط.
    """
    if not secret:
        return False
    if uses_second_factor(actor):
        import pyotp

        from core.views_auth import usable_totp_secret

        code = secret.strip().replace(" ", "")
        if not pyotp.TOTP(usable_totp_secret(actor)).verify(code, valid_window=1):
            return False
        try:
            return bool(cache.add(_totp_used_key(actor, code), True, timeout=TOTP_REPLAY_SECONDS))
        except state.CACHE_DOWN:
            logger.warning("view_as: totp replay store unavailable for actor %s", actor.pk)
            return False
    return bool(actor.check_password(secret))


def remember_reauth(request: Any, actor: Any) -> None:
    request.session[state.REAUTH_KEY] = state.sign(
        {"a": str(actor.pk), "h": actor.get_session_auth_hash()}, state.REAUTH_SALT
    )


def _failures_key(actor: Any) -> str:
    return f"view_as:reauth_failures:{actor.pk}"


def reauth_locked(actor: Any) -> bool:
    """خمسُ محاولاتٍ خاطئةٍ توقف التأكيدَ ربعَ ساعة — فلا تُخمَّن كلمةُ المطوّر من جلسةٍ مفتوحة.

    وذاكرةٌ لا تشترك فيها العمليّاتُ أو سقط Redis: مقفلٌ — لا يُفتح التأكيدُ بلا عدٍّ يراه كلُّ العمّال.
    """
    if not lock_store_shared():
        return True
    try:
        return int(cache.get(_failures_key(actor)) or 0) >= REAUTH_FAILURES
    except state.CACHE_DOWN:
        logger.warning("view_as: reauth lock store unavailable for actor %s", actor.pk)
        return True


def note_reauth_failure(actor: Any) -> None:
    key = _failures_key(actor)
    try:
        cache.add(key, 0, timeout=REAUTH_LOCK_SECONDS)
        try:
            cache.incr(key)
        except ValueError:  # انقضى المفتاحُ بين add وincr
            cache.set(key, 1, timeout=REAUTH_LOCK_SECONDS)
    except state.CACHE_DOWN:  # التالي يقرأ القفلَ من الذاكرة الساقطة نفسِها فيُقفل
        logger.warning("view_as: reauth failure not counted for actor %s", actor.pk)


def clear_reauth_failures(actor: Any) -> None:
    try:
        cache.delete(_failures_key(actor))
    except state.CACHE_DOWN:
        logger.warning("view_as: reauth failures not cleared for actor %s", actor.pk)


# ── الدخولُ والخروج ──────────────────────────────────────────────


def _switch_session(request: Any, user: Any, backend: str) -> None:
    """يجعل الجلسةَ لـ`user` بلا `login()`: مفتاحٌ جديدٌ ورمزُ CSRF جديد، والبياناتُ الأخرى باقية."""
    request.session.cycle_key()
    request.session[SESSION_KEY] = user._meta.pk.value_to_string(user)
    request.session[BACKEND_SESSION_KEY] = backend
    request.session[HASH_SESSION_KEY] = user.get_session_auth_hash()
    rotate_token(request)
    request.user = user


def enter(request: Any, actor: Any, link: Any) -> state.ViewAs:
    """ينقل الجلسةَ إلى الحساب المرتبط — بعد التحقّق كلِّه عند المستدعي."""
    from core.views_auth import PRIMARY_AUTH_BACKEND

    if link.confirmed_at is None:
        link.confirmed_at = timezone.now()
        link.save(update_fields=["confirmed_at", "updated_at"])
    started = state.now()
    backend = request.session.get(BACKEND_SESSION_KEY) or PRIMARY_AUTH_BACKEND
    target = link.target
    _switch_session(request, target, backend)
    request.session[state.LINKED_KEY] = state.sign(
        {
            "a": str(actor.pk),
            "h": actor.get_session_auth_hash(),
            "t": str(target.pk),
            "l": str(link.pk),
            "s": started,
            "b": backend,
        },
        state.LINKED_SALT,
    )
    request.session[state.LINKED_SEEN_KEY] = started
    return state.ViewAs(
        kind=state.LINKED,
        actor_id=str(actor.pk),
        started=started,
        target_id=str(target.pk),
        link_id=str(link.pk),
    )


def restore(request: Any, actor: Any, payload: dict[str, Any]) -> None:
    """يعيد الجلسةَ إلى المطوّر — «الخروجُ يعيد المطوّرَ لا يُخرجه»."""
    _switch_session(request, actor, payload.get("b") or "")
    request.session.pop(state.LINKED_KEY, None)
    request.session.pop(state.LINKED_SEEN_KEY, None)


def current_payload(request: Any) -> dict[str, Any] | None:
    return state.unsign(request.session.get(state.LINKED_KEY), state.LINKED_SALT)


def resume(request: Any) -> tuple[str, Any, dict[str, Any] | None]:
    """يفحص الانتحالَ القائم في كلّ طلب ويعيد `(الحكم، المطوّر، الحمولة)`.

    الأحكام: `ok` يستمرّ، و`restore` يعود المطوّرُ (بسببٍ في الحمولة `why`)، و`logout` تُغلق الجلسةُ كلُّها.
    """
    from core.models import CustomUser, LinkedAccount

    payload = current_payload(request)
    if payload is None:
        return "logout", None, None
    actor = CustomUser.objects.filter(pk=payload.get("a")).first()
    if (
        actor is None
        or not actor.is_active
        or actor.get_session_auth_hash() != payload.get("h")
        or not has_unrestricted_role(actor)
    ):
        return "logout", actor, payload
    if str(request.user.pk) != payload.get("t"):
        return "logout", actor, payload
    linked = LinkedAccount.objects.filter(
        pk=payload.get("l"), developer=actor, target_id=payload.get("t"), is_active=True
    ).exists()
    moment = state.now()
    started = int(payload.get("s") or 0)
    seen = int(request.session.get(state.LINKED_SEEN_KEY) or started)
    if not linked:
        return "restore", actor, {**payload, "why": "link_revoked"}
    if moment - started > LINKED_CAP_SECONDS:
        return "restore", actor, {**payload, "why": "cap"}
    if moment - seen > LINKED_IDLE_SECONDS:
        return "restore", actor, {**payload, "why": "idle"}
    request.session[state.LINKED_SEEN_KEY] = moment
    return "ok", actor, payload


def end_everything(request: Any) -> None:
    """علامةٌ لا تثبت أو مطوّرٌ لم يعد كما كان: لا يُعاد أحدٌ إلى أحد — تُغلق الجلسة."""
    logout(request)

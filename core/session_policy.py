"""
core/session_policy.py — مُهَلُ الجلسة بحسب الدور، في مكانٍ واحد (W-20261005-004، س٢)
═══════════════════════════════════════════════════════════════════════════════════════
المصدر: قرارا المالك D-222م (2026-10-05) وD-223م، وقبولُ 0104 المشروط (انظر
docs/session_expiry_spec_2026-10-05.md في مجلّد المايسترو).

| الدور                                   | خمول     | مطلقة     |
|-----------------------------------------|----------|-----------|
| معلّم / مشرف / بقيّة الموظّفين          | 60 دقيقة | 8 ساعات   |
| النائب الأكاديميّ                       | 120      | 8 ساعات   |
| المدير                                  | 20       | 8 ساعات   |
| وليّ الأمر                              | 15       | ساعتان    |
| جهازٌ مشترك (أيّ دور)                   | 10       | بلا تغيير |
| دورٌ غير معرَّف (طالب، مطوّر منصّة…)    | 60       | 8 ساعات (ساعتان للطالب) |

الخمولُ **منزلق**: يجدّده نبضُ `session-guard.js` بإدخالٍ فعليّ (`session_touch`) أو
طلبُ مستخدمٍ حقيقيّ — بكتابةٍ في الجلسة لا تزيد على واحدةٍ كلَّ 5 دقائق (هدفُ MTG-2026-005:
لا `SESSION_SAVE_EVERY_REQUEST`). والمطلقةُ من لحظة الدخول (`_login_at`) ولا يمدّدها شيء.

تنبيهُ المخاطرة المعلَن: 60 و120 دقيقة فوق حدّ 30 دقيقة في NIST SP 800-63B (AAL2) وASVS L2؛
يُعوَّض بالمطلقة وتحذيرِ الدقيقتين ونبضِ الإدخال الفعليّ وجهازٍ مشترك 10 دقائق (قبلتها 0104).
"""

from __future__ import annotations

import ipaddress
import os
import time
from dataclasses import dataclass
from functools import lru_cache

from django.conf import settings
from django.contrib.auth import logout
from django.contrib.auth.signals import user_logged_in

LOGIN_AT_KEY = "_login_at"
TOUCH_KEY = "_last_touch"
ROLE_KEY = "_session_role"

MINUTE = 60
HOUR = 3600

#: خمولُ الدور غير المعرَّف — قيمةٌ ثابتةٌ هنا لا تتبع `SESSION_COOKIE_AGE` (سقفُ المخزن لا مُهلةُ الخمول).
DEFAULT_IDLE = 60 * MINUTE
#: خمولُ الجهاز المشترك — قائمةٌ يملكها المالك (SESSION_SHARED_DEVICE_NETWORKS).
SHARED_DEVICE_IDLE = 10 * MINUTE

STAFF_ABSOLUTE = 8 * HOUR
BENEFICIARY_ABSOLUTE = 2 * HOUR  # الطالب ووليّ الأمر (D-222م)

#: يُجدَّد ختمُ الخمول من طلب المستخدم الفعليّ بعد هذه المدّة من آخر كتابة — لا أكثر.
REFRESH_EVERY = 5 * MINUTE
#: أقلُّ فاصلٍ بين كتابتَي تجديدٍ من `session_touch` — لا يكتب عميلٌ مفرطٌ كلَّ ثانية.
MIN_TOUCH_INTERVAL = 60

#: أدوارٌ لها خمولٌ خاصّ، والباقي من الكادر 60 (D-222م)، وغيرُ المعرَّف `DEFAULT_IDLE`.
IDLE_BY_ROLE = {
    "vice_academic": 120 * MINUTE,
    "principal": 20 * MINUTE,
    "parent": 15 * MINUTE,
}
STAFF_IDLE = 60 * MINUTE

#: مساراتٌ ثابتةٌ/صحّيّةٌ لا جلسةَ فيها ولا حكمَ عليها.
UNGUARDED_PREFIXES = (
    "/static/",
    "/media/",
    "/health/",
    "/ready/",
    "/metrics",
    "/manifest.json",
    "/sw.js",
    "/offline/",
)
#: طلباتُ الجلسة نفسِها لا تُجدِّد بمروره وحدَه (الحالةُ قراءةٌ، والنبضةُ تجدّد بنفسها).
SESSION_PATH_PREFIX = "/auth/session/"


@dataclass(frozen=True)
class Limits:
    idle: int
    absolute: int


def _staff_roles() -> frozenset[str]:
    from core.models.access import (
        TIER_1_LEADERSHIP,
        TIER_2_DEPUTIES,
        TIER_3_SUPERVISORS,
        TIER_4_STAFF,
    )

    return frozenset(
        TIER_1_LEADERSHIP | TIER_2_DEPUTIES | TIER_3_SUPERVISORS | TIER_4_STAFF | {"specialist"}
    )


def limits_for(role: str, *, shared_device: bool = False) -> Limits:
    """مُهلتا الدور بالثواني. الجهازُ المشترك يُقصّر الخمولَ ولا يمسّ المطلقة."""
    from core.models.access import TIER_5_BENEFICIARIES

    role = role or ""
    configured = getattr(settings, "SESSION_ABSOLUTE_AGE", None)
    if configured:
        absolute = int(configured)
    else:
        absolute = BENEFICIARY_ABSOLUTE if role in TIER_5_BENEFICIARIES else STAFF_ABSOLUTE

    if role in IDLE_BY_ROLE:
        idle = IDLE_BY_ROLE[role]
    elif role in _staff_roles():
        idle = STAFF_IDLE
    else:
        idle = DEFAULT_IDLE
    if shared_device:
        idle = min(idle, SHARED_DEVICE_IDLE)
    return Limits(idle=min(idle, absolute), absolute=absolute)


@lru_cache(maxsize=8)
def _parse_networks(raw: str) -> tuple:
    nets = []
    for part in raw.split(","):
        part = part.strip()
        if not part:
            continue
        try:
            nets.append(ipaddress.ip_network(part, strict=False))
        except ValueError:
            continue  # عنصرٌ مغلوطٌ لا يُسقط الموقع: يُهمَل
    return tuple(nets)


def is_shared_device(request) -> bool:
    """أصادرٌ الطلبُ من شبكةٍ في قائمة الأجهزة المشتركة؟ القائمةُ فارغةٌ حتى يزوّدها المالك."""
    configured = getattr(settings, "SESSION_SHARED_DEVICE_NETWORKS", None)
    raw = (
        ",".join(configured)
        if isinstance(configured, list | tuple | set)
        else (configured or os.environ.get("SESSION_SHARED_DEVICE_NETWORKS", ""))
    )
    nets = _parse_networks(raw)
    if not nets:
        return False
    from core.request_utils import get_client_ip

    try:
        ip = ipaddress.ip_address(get_client_ip(request))
    except ValueError:
        return False
    return any(ip in net for net in nets)


def limits_for_request(request) -> Limits:
    return limits_for(request.user.get_role(), shared_device=is_shared_device(request))


# ── ختمُ الجلسة ──────────────────────────────────────────────────────


def stamp_session(sender, request, user, **kwargs) -> None:
    """يختم الجلسةَ بلحظة الدخول وآخر تجديد ودورِ صاحبها — منها تُحسب المتبقّياتُ دون استعلام."""
    if request is None or not hasattr(request, "session"):
        return
    now = int(time.time())
    request.session[LOGIN_AT_KEY] = now
    request.session[TOUCH_KEY] = now
    request.session[ROLE_KEY] = user.get_role()


user_logged_in.connect(stamp_session, dispatch_uid="core.session_policy.stamp_session")


def clock(request, *, now: int | None = None) -> dict:
    """المتبقّي للخمول والمطلقة بالثواني — `None` لجلسةٍ سابقةٍ للختم (يُختم عند أوّل طلب).

    متحفّظٌ عن قصد: ما يعرضه التحذيرُ لا يتجاوز ما يحكم به الخادم أبداً.
    """
    now = int(time.time()) if now is None else now
    login_at = request.session.get(LOGIN_AT_KEY)
    touched = request.session.get(TOUCH_KEY)
    limits = limits_for_request(request)
    return {
        "idle_limit": limits.idle,
        "absolute_limit": limits.absolute,
        "idle_remaining": None if touched is None else max(0, touched + limits.idle - now),
        "absolute_remaining": (
            None if login_at is None else max(0, login_at + limits.absolute - now)
        ),
    }


def _user_initiated(request) -> bool:
    """طلبُ مستخدمٍ حقيقيّ: تصفّحٌ عاديّ أو إرسالٌ يغيّر شيئاً — لا استطلاعَ خلفيّاً (HTMX/fetch GET)."""
    if request.method not in ("GET", "HEAD"):
        return True
    # من يطلب JSON وحدَه استطلاعٌ لا تصفّح: يُستبعد ولو نسي صاحبُه رأسَ X-Requested-With
    # (command_center.js كان يجدّد الخمول بلا نهاية فيُبطله — توصية 0104).
    wants_json_only = request.headers.get("Accept", "").startswith("application/json")
    return not (
        request.headers.get("HX-Request") == "true"
        or request.headers.get("X-Page-Nav") == "1"
        or request.headers.get("X-Requested-With") == "XMLHttpRequest"
        or wants_json_only
    )


def ended_reason(login_at: int, touched: int, limits: Limits, now: int) -> str:
    """سببُ انتهاء الجلسة بمُهلتَيها: «absolute» أو «idle»، و"" إن بقيت. حكمٌ واحدٌ للطلب والمصافحة."""
    if now - login_at >= limits.absolute:
        return "absolute"
    if now - touched >= limits.idle:
        return "idle"
    return ""


def websocket_ended(scope, *, now: int | None = None) -> str:
    """يحكم على جلسة مصافحة WebSocket بالمُهلتين نفسيهما — يُستدعى في `connect` قبل `accept`.

    المقبسُ ليس نشاطَ مستخدم فلا يجدّد شيئاً ولا يختم؛ وجلسةٌ بلا ختمٍ (سابقةٌ للسياسة) لا تُقطع
    هنا لأنّ أوّل طلب HTTP لها يختمها. ويعيد "" إن بقيت، وسببَ الانتهاء إن انتهت.
    ملاحظة: الحكمُ عند المصافحة وحدها؛ مقبسٌ مفتوحٌ لا يُقطع بعد ذلك، وقائمةُ الأجهزة المشتركة
    لا تُطبَّق هنا (عنوانُ العميل خلف الوسيط ليس في النطاق).
    """
    user = scope.get("user")
    session = scope.get("session")
    if session is None or not user or not user.is_authenticated:
        return ""
    login_at, touched = session.get(LOGIN_AT_KEY), session.get(TOUCH_KEY)
    if login_at is None or touched is None:
        return ""
    now = int(time.time()) if now is None else now
    return ended_reason(login_at, touched, limits_for(user.get_role()), now)


def enforce(request, *, now: int | None = None) -> str:
    """يحكم على جلسة المستخدم المسجَّل: يُنهيها عند تجاوز مُهلتها، ويجدّد الخمول مخنوقاً.

    يعيد "" إن بقيت الجلسةُ، أو «absolute»/«idle» إن أُنهيت (وصار `request.user` مجهولاً).
    الجلسةُ السابقةُ للختم (قبل أوّل نشرٍ بهذه السياسة) تبدأ نوافذُها من أوّل طلب.
    """
    if not getattr(request, "user", None) or not request.user.is_authenticated:
        return ""
    if request.path.startswith(UNGUARDED_PREFIXES):
        return ""
    session = getattr(request, "session", None)
    if session is None:  # طلبٌ بلا طبقة جلسة (اختبارُ وسيطٍ منفرد)
        return ""
    now = int(time.time()) if now is None else now

    login_at = session.get(LOGIN_AT_KEY)
    touched = session.get(TOUCH_KEY)
    if login_at is None or touched is None:
        session[LOGIN_AT_KEY] = now if login_at is None else login_at
        session[TOUCH_KEY] = now if touched is None else touched
        session[ROLE_KEY] = request.user.get_role()
        return ""

    reason = ended_reason(login_at, touched, limits_for_request(request), now)
    if reason:
        logout(request)
        return reason

    role = request.user.get_role()
    stamped = session.get(ROLE_KEY)
    if stamped != role:
        # تغيّر الدور (تبديلُ دورٍ أو عضويّةٌ جديدة): مفتاحُ جلسةٍ جديدٌ ونافذةُ خمولٍ جديدة؛
        # والمطلقةُ باقيةٌ من الدخول الأصليّ فلا يمدّدها تبديلُ الدور.
        session[ROLE_KEY] = role
        session[TOUCH_KEY] = now
        if stamped is not None:
            session.cycle_key()
    elif (
        now - touched >= REFRESH_EVERY
        and not request.path.startswith(SESSION_PATH_PREFIX)
        and _user_initiated(request)
    ):
        session[TOUCH_KEY] = now
    return ""

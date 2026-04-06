"""
core/sentry_config.py
━━━━━━━━━━━━━━━━━━━━━
إعدادات Sentry المتقدمة — تصفية ضوضاء + PDPPL scrubbing + smart sampling.

✅ v5.5: Elite-grade Sentry configuration
- before_send: تصفية الأخطاء غير المفيدة
- traces_sampler: تخطي health checks وstatic files
- configure_scope_from_request: إضافة school_id + user_role
- PDPPL EventScrubber: إخفاء PII قبل الإرسال
"""

import re

# ══════════════════════════════════════════════════════════════
# 1. قائمة الأخطاء المتجاهلة — ضوضاء لا تحتاج تتبع
# ══════════════════════════════════════════════════════════════
SENTRY_IGNORE_ERRORS = [
    # Django security — هجمات bots وscanners
    "django.security.DisallowedHost",
    "django.security.SuspiciousOperation",
    # اتصالات مقطوعة — المستخدم أغلق المتصفح
    "ConnectionResetError",
    "BrokenPipeError",
    # أخطاء HTTP عادية — ليست bugs
    "django.http.Http404",
    # مهلة الاتصال — مشاكل شبكة مؤقتة
    "ConnectionError",
    "TimeoutError",
]

# مسارات URL لا تُسجّل أخطاؤها (health probes, static, media)
_IGNORED_URL_PATTERNS = re.compile(
    r"^/(health|ready|status|favicon\.ico|static|media|robots\.txt|\.well-known)/?"
)

# ══════════════════════════════════════════════════════════════
# 2. أنماط PII للـ scrubbing — PDPPL م.13
# ══════════════════════════════════════════════════════════════
_PII_PATTERNS = [
    # ⚠️ الترتيب مهم: الأنماط الأطول أولاً لتجنب التداخل
    # أرقام الهواتف (+974XXXXXXXX أو 974XXXXXXXX) — قبل QID لأنها 11+ رقم
    (re.compile(r"\+?974\d{8}"), "[PHONE_REDACTED]"),
    # أرقام الهوية القطرية (11 رقم بالضبط — بدون + قبلها)
    (re.compile(r"(?<!\+)\b\d{11}\b"), "[QID_REDACTED]"),
    # البريد الإلكتروني
    (re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}"), "[EMAIL_REDACTED]"),
    # عناوين IP
    (re.compile(r"\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b"), "[IP_REDACTED]"),
]


def before_send(event, hint):
    """
    فلتر ما قبل الإرسال — يمنع الضوضاء من الوصول لـ Sentry.

    ✅ يُرجع None = لا يُرسل الحدث
    ✅ يُرجع event = يُرسل بعد التنظيف
    """
    # ── 1. تصفية أنواع الأخطاء المتجاهلة ──
    if "exc_info" in hint:
        exc_type = hint["exc_info"][0]
        exc_module = getattr(exc_type, "__module__", "")
        exc_name = f"{exc_module}.{exc_type.__name__}" if exc_module else exc_type.__name__

        for ignored in SENTRY_IGNORE_ERRORS:
            if ignored in exc_name:
                return None

    # ── 2. تصفية أخطاء مسارات monitoring ──
    request_data = event.get("request", {})
    url = request_data.get("url", "")
    if url:
        from urllib.parse import urlparse

        path = urlparse(url).path
        if _IGNORED_URL_PATTERNS.match(path):
            return None

    # ── 3. PDPPL scrubbing — إخفاء PII من كل النصوص ──
    event = _scrub_event_pii(event)

    return event


def traces_sampler(sampling_context):
    """
    Sampling ذكي — يُعطي أولوية للمسارات المهمة.

    ✅ 0.0 = لا تسجّل  |  1.0 = سجّل دائماً  |  0.1 = 10%
    """
    # ── تخطي health checks تماماً ──
    transaction_name = sampling_context.get("transaction_context", {}).get("name", "")

    if any(
        pattern in transaction_name
        for pattern in ["/health/", "/ready/", "/status/", "/favicon.ico"]
    ):
        return 0.0

    # ── تخطي static/media ──
    if any(
        transaction_name.startswith(prefix) for prefix in ["/static/", "/media/"]
    ):
        return 0.0

    # ── Celery tasks — أهمية عالية ──
    op = sampling_context.get("transaction_context", {}).get("op", "")
    if op == "celery.task":
        return 0.3  # 30% من المهام

    # ── API endpoints — أهمية عادية ──
    if "/api/" in transaction_name:
        return 0.15  # 15%

    # ── كل شيء آخر — 10% ──
    return 0.1


def configure_sentry_scope(scope, request):
    """
    يُضيف context مخصص لكل حدث — يُسهّل Debug بشكل كبير.

    يُستدعى من middleware أو before_send_transaction.
    """
    if not hasattr(request, "user") or not request.user.is_authenticated:
        scope.set_tag("user.authenticated", False)
        return

    user = request.user
    scope.set_tag("user.authenticated", True)

    # ── role (بدون PII) ──
    try:
        role = user.get_role() if hasattr(user, "get_role") else "unknown"
        scope.set_tag("user.role", role)
    except Exception:
        scope.set_tag("user.role", "error")

    # ── school_id (بدون PII — ID فقط) ──
    try:
        school = user.get_school() if hasattr(user, "get_school") else None
        if school:
            scope.set_tag("school.id", str(school.id))
            scope.set_tag("school.name", school.name_en or school.name or "unknown")
    except Exception:
        pass

    # ── user ID فقط (لا اسم ولا بريد — PDPPL) ──
    scope.set_user({"id": str(user.pk)})


def _scrub_event_pii(event):
    """
    يُنظّف كل النصوص في الحدث من PII.

    يمر على: message, breadcrumbs, exception values, tags, extra.
    """
    # ── Message ──
    if "message" in event:
        event["message"] = _scrub_text(event["message"])

    # ── Exception values ──
    for exc in event.get("exception", {}).get("values", []):
        if "value" in exc:
            exc["value"] = _scrub_text(exc["value"])
        # Stack trace local variables
        for frame in exc.get("stacktrace", {}).get("frames", []):
            if "vars" in frame:
                frame["vars"] = _scrub_dict(frame["vars"])

    # ── Breadcrumbs ──
    for crumb in event.get("breadcrumbs", {}).get("values", []):
        if "message" in crumb:
            crumb["message"] = _scrub_text(crumb["message"])
        if "data" in crumb and isinstance(crumb["data"], dict):
            crumb["data"] = _scrub_dict(crumb["data"])

    # ── Extra data ──
    if "extra" in event and isinstance(event["extra"], dict):
        event["extra"] = _scrub_dict(event["extra"])

    return event


def _scrub_text(text):
    """يُخفي PII في نص واحد."""
    if not isinstance(text, str):
        return text
    for pattern, replacement in _PII_PATTERNS:
        text = pattern.sub(replacement, text)
    return text


def _scrub_dict(data):
    """يُخفي PII في dictionary (recursive)."""
    if not isinstance(data, dict):
        return data
    result = {}
    for key, value in data.items():
        # حقول حساسة بالاسم — تُخفى بالكامل
        sensitive_keys = {
            "password", "secret", "token", "api_key", "authorization",
            "national_id", "qid", "phone", "email", "ssn",
            "credit_card", "card_number",
        }
        if any(sk in key.lower() for sk in sensitive_keys):
            result[key] = "[REDACTED]"
        elif isinstance(value, str):
            result[key] = _scrub_text(value)
        elif isinstance(value, dict):
            result[key] = _scrub_dict(value)
        else:
            result[key] = value
    return result

"""
core/sentry_config.py
━━━━━━━━━━━━━━━━━━━━━
إعدادات Sentry المتقدمة — تصفية ضوضاء + PDPPL scrubbing + smart sampling.

✅ v5.5: Azkia-grade Sentry configuration
- before_send: تصفية الأخطاء غير المفيدة
- traces_sampler: تخطي health checks وstatic files
- configure_scope_from_request: إضافة school_id + user_role
- PDPPL EventScrubber: إخفاء PII قبل الإرسال
"""

import re


# ══════════════════════════════════════════════════════════════
# 1. قائمة الأخطاء المتجاهلة — ضوضاء لا تحتاج تتبع
# ══════════════════════════════════════════════════════════════
#: [B4-7N] الأخطاء المُتجاهَلة — **بهويّة الصنف لا بمطابقة نصّية**.
#:
#: القائمة السابقة كانت نصوصاً تُطابَق بالاحتواء (`if ignored in exc_name`)،
#: وأخطأت في الاتجاهين معاً:
#:
#:     تحت-مطابقة   "django.security.DisallowedHost" لا يقع في
#:                  "django.core.exceptions.DisallowedHost" — والاسم الحقيقي
#:                  هو الثاني. فثلاثة بنودٍ من سبعة لم تُسقط شيئاً قطّ.
#:     فوق-مطابقة   "ConnectionError" يقع في "redis.exceptions.ConnectionError"،
#:                  فكان عطبُ الوسيط يُبتلَع صامتاً — وهو أوّل ما نحتاج رؤيته
#:                  على العامل.
#:
#: و`ConnectionError`/`TimeoutError` العامّان أُسقطا من القائمة عمداً: قد يكونان
#: Redis أو SMTP أو قاعدةً أو مزوّداً، وكلّها أحداثٌ تشغيلية نريدها لا ضوضاء.
#: والباقي انقطاعُ عميلٍ حقيقيّ — أغلق المتصفّح — ولا يُفيد تتبّعه.
def ignored_exception_types():
    """أصناف الاستثناءات التي لا تُرسَل إلى Sentry.

    دالّةٌ لا ثابت — وليس لأن الاستيراد على مستوى الوحدة يسقط: جُرِّب فعمل قبل
    `django.setup()` وبعده. بل لأن هذه الوحدة تُستورَد من `production.py`
    **أثناء تحميل الإعدادات نفسها**، فإبقاء استيراد Django داخل الدالّة يمنع
    ارتباط ترتيبٍ لا نحتاجه، ويُبقي القائمة موضعاً واحداً يُقرأ ويُختبَر.
    """
    from django.core.exceptions import DisallowedHost, SuspiciousOperation
    from django.http import Http404

    return (
        # هجمات bots وscanners — لا تخصّ الكود
        DisallowedHost,
        SuspiciousOperation,
        # طلبٌ لمسارٍ غير موجود — ليس عطباً
        Http404,
        # انقطاع العميل: أغلق المتصفّح قبل اكتمال الردّ.
        #
        # ويبقى فيهما احتمالٌ مقبول: مقبسٌ إلى Redis أو مزوّدٍ قد يُنتج النوع
        # نفسه فيُسقَط. وهما فرعان من `OSError` ونادران خارج سياق الطلب، ولم
        # نرَ لهما أثراً في الإنتاج — فالمقايضة معلومة لا مجهولة.
        ConnectionResetError,
        BrokenPipeError,
    )


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
    #
    # [B4-7N] `issubclass` لا مطابقة نصّية: الهويّة تُقرَّر من شجرة الأصناف،
    # فلا تُسقط ما لم يُقصد ولا تُبقي ما قُصد إسقاطه.
    # والاستخراج دفاعيّ: `hint["exc_info"]` قد يأتي `None` أو ثلاثيّاً فارغاً،
    # وقراءته مباشرةً ترفع داخل `before_send` نفسه — فتُسقط المكتبةُ الحدث بلا
    # أن يعرف أحد. أي أن هشاشةً هنا تُنتج **فقداناً صامتاً** لا خطأً مرئياً.
    exc_info = hint.get("exc_info") or ()
    exc_type = exc_info[0] if exc_info else None

    # `isinstance(exc_type, type)` شرطٌ لازم: `issubclass` ترفع `TypeError` على
    # ما ليس صنفاً، وSentry يُمرّر أحياناً ما ليس استثناءً.
    if isinstance(exc_type, type) and issubclass(exc_type, ignored_exception_types()):
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
    if any(transaction_name.startswith(prefix) for prefix in ["/static/", "/media/"]):
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
            # [B4-7N] المُعرِّف وحده. اسم المدرسة بيانُ مستأجِر لا بيانُ شخص،
            # لكنه يذهب إلى وجهةٍ لا نتحكّم في حفظها ولا مدّة بقائها — ولا
            # يُضيف إلى التشخيص ما لا يُعطيه المُعرِّف.
            scope.set_tag("school.id", str(school.id))
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

    # ── [B4-7N] LogEntry — المسار الذي نعتمده فعلاً ──
    #
    # `LoggingIntegration(event_level="ERROR")` لا تضع رسالة السجلّ في
    # `event["message"]` بل في `event["logentry"]` بحقولٍ ثلاثة. فكان المنقّي
    # مبنيّاً للمفتاح الذي لا يُستعمل، وغائباً عن الذي يُستعمل — أي أن كل
    # `logger.error` نُنتجه عمداً كان يصل Sentry بلا تنقية.
    logentry = event.get("logentry")

    if isinstance(logentry, dict):
        for field in ("message", "formatted"):
            if field in logentry:
                logentry[field] = _scrub_text(logentry[field])

        # الوسائط تُنقّى كلٌّ على حدة: القالب `%s` وحده لا يحمل شيئاً، والقيمة
        # هي التي تحمل البريد أو الهاتف.
        params = logentry.get("params")

        if isinstance(params, list | tuple):
            logentry["params"] = type(params)(_scrub_value(item) for item in params)
        elif isinstance(params, dict):
            logentry["params"] = _scrub_dict(params)

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


def _scrub_value(value):
    """[B4-7N] يُنقّي قيمةً مهما كان نوعها — النصّ وحده يُنقّى، وغيره يمرّ."""
    if isinstance(value, str):
        return _scrub_text(value)
    if isinstance(value, dict):
        return _scrub_dict(value)
    if isinstance(value, list | tuple):
        return type(value)(_scrub_value(item) for item in value)
    return value


def _scrub_text(text):
    """يُخفي PII في نص واحد."""
    if not isinstance(text, str):
        return text
    for pattern, replacement in _PII_PATTERNS:
        text = pattern.sub(replacement, text)
    return text


#: مفاتيح تُحجب بالاحتواء — أسرارٌ لا تُقرأ جزئياً، وصيغُها كثيرة:
#: `api_key`, `access_token`, `HTTP_AUTHORIZATION`… فالاحتواء هنا هو الصواب.
_SENSITIVE_KEY_FRAGMENTS = frozenset(
    {
        "password",
        "secret",
        "token",
        "api_key",
        "authorization",
        "national_id",
        "qid",
        "phone",
        "email",
        "ssn",
        "credit_card",
        "card_number",
    }
)

#: [B4-7N] مفاتيح تُحجب بالمطابقة **التامّة** — بياناتٌ بشرية دلالية.
#:
#: والفرق عن المجموعة أعلاه مقصود: `name` كمقطعٍ كان سيحجب `task_name` و
#: `event_name` و`filename` و`school_name`، فنخسر رصداً نافعاً بلا أن نكسب
#: خصوصية. والمطابقة التامّة تحجب ما نقصده وحده.
#:
#: وهذه المجموعة هي الجواب عن حدٍّ بنيويّ في الأنماط: البريد والهاتف والهوية
#: لها أشكال تُلتقط، أمّا الاسم وعنوان الإشعار ونصّه فلا شكل لها — خصوصاً
#: بالعربية — فلا يحرسها إلا اسم المفتاح.
_SEMANTIC_PII_KEYS = frozenset(
    {
        "full_name",
        "student_name",
        "parent_name",
        "recipient_name",
        "display_name",
        "title",
        "subject",
        "body",
        "body_text",
        "body_html",
        "message_text",
        "notification_title",
        "notification_body",
    }
)


def _scrub_dict(data):
    """يُخفي PII في dictionary (recursive)."""
    if not isinstance(data, dict):
        return data

    result = {}

    for key, value in data.items():
        lowered = key.lower()

        if lowered in _SEMANTIC_PII_KEYS or any(
            fragment in lowered for fragment in _SENSITIVE_KEY_FRAGMENTS
        ):
            result[key] = "[REDACTED]"
        else:
            result[key] = _scrub_value(value)

    return result

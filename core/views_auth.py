import base64
import logging
from datetime import timedelta
from io import BytesIO

import django.db
import pyotp
import qrcode
from django.conf import settings
from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import F
from django.shortcuts import redirect, render
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST
from django_ratelimit.decorators import ratelimit

from core.auth_identity import identifier_kind, lockout_key, resolve_user
from core.mfa_session import mark_verified
from core.models import AuditLog, CustomUser
from core.models.access import TIER_5_BENEFICIARIES
from core.privacy import mask_national_id

logger = logging.getLogger(__name__)

#: محاولاتٌ فاشلةٌ قبل القفل، ومدّتُه — لكلمة المرور ولرمز التحقّق سواء.
#: والمدّةُ تساوي `AXES_COOLOFF_TIME` في الإعدادات (قرار 2026-09-14: خمسُ دقائق).
FAILURES_BEFORE_LOCK = 5
LOCK_MINUTES = 5

#: المعرّفُ بالأرقام اللاتينيّة وحدها (قرار 2026-09-14). و`str.isdigit` يقبل ١٢٣
#: ويقبل ۱۲۳، والبحثُ في القاعدة لا يطابقها — فكانت تُردّ «غير صحيحة» بلا تفسير.
LATIN_DIGITS_ONLY = "اكتب المعرّف بالأرقام الإنجليزية 0–9 — لا بالأرقام العربية."


def _non_latin_digits(identifier: str) -> bool:
    return any(ch.isdigit() and not ch.isascii() for ch in identifier)


def _release_expired_lock(user: CustomUser) -> None:
    """قفلٌ انتهت مدّتُه يُرفع ويبدأ العدُّ من الصفر.

    وإلّا بقي العدّادُ عند حدّه، فأوّلُ خطأٍ بعد انقضاء المدّة يقفل الحسابَ فوراً
    من جديد — فلا تكون المدّةُ مدّةً بل بابٌ يُغلق على من يجرّب مرّةً واحدة.
    وaxes يفعل هذا من نفسه: محاولاتٌ مضت مدّتُها تُنسى.
    """
    if user.locked_until and user.locked_until <= timezone.now():
        CustomUser.objects.filter(pk=user.pk).update(failed_login_attempts=0, locked_until=None)
        user.failed_login_attempts = 0
        user.locked_until = None


def _count_failure(user) -> bool:
    """يزيد عدّادَ الفشل على الحساب ويقفله عند الحدّ — ويعيد هل قُفل الآن.

    قفلٌ صفّيٌّ بـ`select_for_update`: محاولتان متزامنتان لا تضيع إحداهما.
    ورمزُ التحقّق الخاطئ يُعدّ كالكلمة الخاطئة: من جاوز كلمةَ المرور ووقف
    عند الرمز يجرّب ستّةَ أرقامٍ لا كلمة — والعدّادُ واحدٌ لكليهما.
    """
    with transaction.atomic():
        CustomUser.objects.filter(pk=user.pk).select_for_update().update(
            failed_login_attempts=F("failed_login_attempts") + 1
        )
        fresh = CustomUser.objects.get(pk=user.pk)
        if fresh.failed_login_attempts >= FAILURES_BEFORE_LOCK:
            fresh.locked_until = timezone.now() + timedelta(minutes=LOCK_MINUTES)
            fresh.save(update_fields=["locked_until"])
            return True
    return False


def _log_login_failure(request, candidate, identifier: str, *, locked: bool) -> None:
    """أثرُ محاولةٍ فاشلة في سجلّ التدقيق — بلا معرّفٍ خام.

    الحسابُ إن عُرف يُربط بالسجلّ (`user`)، والمعرّفُ المكتوبُ يُستر: رقمٌ
    شخصيٌّ خامٌ في سجلٍّ يُقرأ ويُصدَّر كشفٌ لا تدقيق. و«مجهول» حين لا حساب —
    فتعدادُ المحاولات على معرّفاتٍ لا وجودَ لها إشارةُ مسحٍ لا خطأِ طباعة.
    """
    AuditLog.log(
        user=candidate,
        action="login_failed",
        model_name="CustomUser",
        object_id=candidate.pk if candidate else "",
        object_repr=f"محاولة دخول فاشلة — {mask_national_id(identifier) or 'بلا معرّف'}",
        changes={
            "known": candidate is not None,
            "identifier_kind": identifier_kind(candidate, identifier),
            "locked": locked,
        },
        request=request,
    )


def _axes_reset(request, key: str) -> None:
    """إعادةُ تعيين عدّاد axes بعد دخولٍ ناجح — بالمفتاح المعياريّ لا بالنصّ المكتوب.

    يُكمّل `AXES_RESET_ON_SUCCESS=True` بإعادةٍ صريحة. والمفتاحُ من
    `auth_identity.lockout_key` — وإلّا بقي عدّادُ المعرّف الآخر قائماً.
    """
    try:
        from axes.helpers import reset_request

        reset_request(request=request, username=key)
    except ImportError:
        pass  # axes غير مثبّت — لا مشكلة


def _safe_redirect(url, request, fallback="dashboard"):
    """تحقق من أن الـ redirect URL آمن — يمنع Open Redirect attacks."""
    if url and url_has_allowed_host_and_scheme(
        url, allowed_hosts={request.get_host()}, require_https=request.is_secure()
    ):
        return redirect(url)
    return redirect(fallback)


#: كانت الثنائيّةُ للقيادة وحدَها — وقرارُ 2026-09-14: لكلّ الكادر. الاسمُ باقٍ
#: لمن يستورده، ومعناه اليوم في `requires_two_factor`.
ROLES_REQUIRING_2FA = {"principal", "vice_admin", "vice_academic", "admin"}


def requires_two_factor(user) -> bool:
    """أعلى الثنائيّةُ على هذا المستخدم؟ — الكادرُ كلُّه، لا الطلبةُ ولا أولياءُ الأمور."""
    return bool(user.is_superuser or user.is_staff_member())


def usable_totp_secret(user) -> str | None:
    """سرُّ TOTP مفكوكاً وصالحاً — أو None إن كان غيرَ مقروء.

    `decrypt_field` تُعيد القيمةَ كما هي حين يفشل الفكُّ (مفتاحٌ آخر، أو نسخةُ
    قاعدةٍ من بيئةٍ أخرى)، فكان الرمزُ يُبنى من النصّ المشفَّر نفسِه: QR لا
    يطابقه رمزٌ أبداً، والتحقّقُ يسقط 500 على «Non-base32». هنا يُفحص الفكُّ
    والصيغةُ معاً، والقرارُ لمن يستدعي.
    """
    import base64
    import binascii

    from core.models import decrypt_field

    stored = user.totp_secret or ""
    if not stored:
        return None
    raw = decrypt_field(stored)
    if not raw or raw == stored and stored.startswith("gAAAA"):
        return None
    try:
        base64.b32decode(raw.upper() + "=" * (-len(raw) % 8), casefold=True)
    except (binascii.Error, ValueError):
        return None
    return raw


#: خلفيّةُ التصديق الأصليّة — تُستعمل إن ضاعت من الجلسة (جلسةٌ سابقةٌ للنشر).
PRIMARY_AUTH_BACKEND = "core.backends.HMACAuthBackend"


def password_expired(user) -> bool:
    """هل مضت مدّةُ التدوير على كلمة مرور هذا المنتسب؟

    المرجعُ آخرُ تغييرٍ مسجَّل، وإن لم يُسجَّل قطّ فتاريخُ إنشاء الحساب — فكلمةُ
    البذر التي لم تُبدَّل منذ شهورٍ منتهيةٌ بحكم التعريف. والسياسةُ من الإعدادات
    (`PASSWORD_ROTATION_DAYS`) والصفرُ يعطّلها؛ ولا تمسّ الطلبةَ وأولياءَ الأمور.
    """
    from django.conf import settings

    days = getattr(settings, "PASSWORD_ROTATION_DAYS", 0) or 0
    if days <= 0:
        return False
    is_staff_member = (
        user.memberships.filter(is_active=True)
        .exclude(role__name__in=TIER_5_BENEFICIARIES)
        .exists()
    )
    if not is_staff_member:
        return False
    reference = user.last_password_change or user.date_joined
    return reference is None or reference < timezone.now() - timedelta(days=days)


def _enforce_rotation(user) -> None:
    """يقلب علمَ الإجبار عند الدخول إن انتهت مدّةُ التدوير — فتتكفّل به آلةُ الإجبار القائمة."""
    if not user.must_change_password and password_expired(user):
        user.must_change_password = True
        user.save(update_fields=["must_change_password"])


# ── رسالة خطأ موحّدة — تمنع User Enumeration ──────────────────────
# لا تغيّر هذه الرسالة ولا تجعلها تختلف بحسب وجود المستخدم من عدمه
_AUTH_ERROR = "المعرّف أو كلمة المرور غير صحيحة"


@ratelimit(key="ip", rate="10/m", method="POST", block=True)
def login_view(request):
    """صفحة تسجيل الدخول — مع حماية من القوة الغاشمة وقفل الحساب."""
    if request.user.is_authenticated:
        return redirect("dashboard")

    if request.method == "POST":
        # الحقلُ صار «المعرّف»، و`national_id` يبقى مقبولاً لنماذجَ محفوظةٍ في
        # المتصفّحات ولاختباراتٍ قائمة — يُقرأ ولا يُعرض.
        identifier = (
            request.POST.get("identifier") or request.POST.get("national_id") or ""
        ).strip()
        password = request.POST.get("password", "").strip()

        if not identifier or not password:
            messages.error(request, "يرجى إدخال المعرّف وكلمة المرور")
            return render(request, "auth/login.html")

        # لا يُعدّ فشلاً ولا يكشف وجودَ حساب: خطأُ لوحة مفاتيحٍ لا تخمينُ كلمة.
        if _non_latin_digits(identifier):
            messages.error(request, LATIN_DIGITS_ONLY)
            return render(request, "auth/login.html")

        candidate = resolve_user(identifier, request)
        if candidate:
            _release_expired_lock(candidate)

        # ── التحقق من قفل الحساب (الرسالة هنا مقبولة لأن القفل يحدث بعد محاولات) ──
        if candidate and candidate.locked_until and candidate.locked_until > timezone.now():
            remaining = int((candidate.locked_until - timezone.now()).total_seconds() // 60) + 1
            messages.error(request, f"الحساب مقفل. حاول بعد {remaining} دقيقة.")
            return render(request, "auth/login.html")

        user = authenticate(request, identifier=identifier, password=password)

        if user:
            user.failed_login_attempts = 0
            user.locked_until = None
            user.save(update_fields=["failed_login_attempts", "locked_until"])
            # ✅ v5.4: إعادة تعيين عداد axes عند تسجيل الدخول الناجح
            _axes_reset(request, lockout_key(identifier, request))
            # أيَّ معرّفٍ استُعمل — تُقاس به نهايةُ النافذة المزدوجة في سجلّ التدقيق.
            # ويُحمَل في الجلسة كذلك لأنّ من عليه 2FA يُسجَّل دخولُه في طلبٍ آخر.
            kind = identifier_kind(user, identifier)
            request.login_identifier_kind = kind

            # الرايةُ تجمّد الثنائيّةَ كلَّها لا الإلزامَ وحدَه (قرار 2026-09-14): مطفأةً لا
            # يُسأل أحدٌ عن رمز — ولو كان مفعِّلاً — ويبقى سرُّه لإعادة التشغيل بلا إعدادٍ جديد.
            if (
                user.totp_enabled
                and requires_two_factor(user)
                and getattr(settings, "TWO_FACTOR_REQUIRED_FOR_STAFF", True)
            ):
                request.session["pending_2fa_user"] = str(user.id)
                request.session["pending_identifier_kind"] = kind
                # `authenticate()` يعلّق على المستخدم اسمَ الخلفيّة التي صدّقته، و`login()`
                # يشترطه حين تتعدّد الخلفيّات. وصفحةُ التحقّق تُحمِّل المستخدمَ من القاعدة
                # من جديد فلا تجده — فيُحمَل هنا في الجلسة إلى هناك.
                request.session["pending_2fa_backend"] = getattr(user, "backend", "")
                return redirect("verify_2fa")

            login(request, user)

            _enforce_rotation(user)
            if user.must_change_password:
                return redirect("force_change_password")

            return _safe_redirect(request.GET.get("next", ""), request)

        else:
            # ── إصلاح User Enumeration ────────────────────────────────────────
            # نزيد العداد بصمت إذا وُجد المستخدم، لكن نُظهر نفس الرسالة دائماً
            # سواء عُرف المعرّف أم لم يُعرف — المهاجم لا يعرف الفرق
            locked = False
            try:
                if candidate:
                    locked = _count_failure(candidate)
            except (django.db.DatabaseError, ValueError) as e:
                logger.exception("فشل تحديث عداد محاولات تسجيل الدخول الفاشلة: %s", e)
            _log_login_failure(request, candidate, identifier, locked=locked)
            if locked:
                # رسالة القفل مقبولة — تظهر فقط بعد 5 محاولات
                messages.error(
                    request,
                    f"تم قفل الحساب لمدة {LOCK_MINUTES} دقيقة بسبب المحاولات المتكررة.",
                )
                return render(request, "auth/login.html")

            # رسالة موحّدة في كل الحالات الأخرى — لا تكشف وجود الحساب
            messages.error(request, _AUTH_ERROR)

    return render(request, "auth/login.html")


@ratelimit(key="ip", rate="5/m", method="POST", block=True)
def verify_2fa(request):
    """التحقق من رمز المصادقة الثنائية TOTP عند تسجيل الدخول."""
    user_id = request.session.get("pending_2fa_user")
    if not user_id:
        return redirect("login")

    try:
        user = CustomUser.objects.get(id=user_id)
    except CustomUser.DoesNotExist:
        return redirect("login")

    if request.method == "POST":
        code = request.POST.get("code", "").strip().replace(" ", "")
        _s = usable_totp_secret(user)
        if _s is None:
            # سرٌّ لا يُقرأ بمفتاح هذه البيئة: لا رمزَ يطابقه، فلا يُترك المستخدمُ يحاول.
            logger.error("TOTP secret unreadable for user %s — needs reset_2fa", user.pk)
            messages.error(
                request,
                "تعذّر قراءة سرّ المصادقة الثنائية لحسابك. اطلب من الإدارة إعادة ضبطها "
                "(الأمر: reset_2fa) ثم أعد الإعداد.",
            )
            return render(request, "auth/verify_2fa.html", {"user": user})
        totp = pyotp.TOTP(_s)

        # ── VULN-001 Fix: TOTP Replay Protection (CWE-294) ──────────
        from django.core.cache import cache

        replay_key = f"totp_used:{user.id}:{code}"
        if cache.get(replay_key):
            messages.error(request, "رمز التحقق مُستخدم بالفعل. انتظر رمزاً جديداً.")
            return render(request, "auth/verify_2fa.html", {"user": user})

        if totp.verify(code, valid_window=1):
            cache.set(replay_key, True, timeout=90)  # يمنع إعادة الاستخدام لـ 90 ثانية
            del request.session["pending_2fa_user"]
            request.login_identifier_kind = request.session.pop(
                "pending_identifier_kind", "unknown"
            )
            # بلا هذا كان `login()` يرفع ValueError («خلفيّاتٌ متعدّدة») فتسقط الصفحةُ 500 —
            # أي أنّ كلَّ من فعّل المصادقةَ الثنائيّة لم يعد يستطيع الدخول.
            backend = request.session.pop("pending_2fa_backend", "") or PRIMARY_AUTH_BACKEND
            login(request, user, backend=backend)
            mark_verified(request)
            _enforce_rotation(user)
            if user.must_change_password:
                return redirect("force_change_password")
            return _safe_redirect(request.GET.get("next", ""), request)
        else:
            # الرمزُ الخاطئ فشلُ دخولٍ كالكلمة الخاطئة: يُعدّ على الحساب نفسِه
            # ويُدقَّق — وإلّا كان الحدُّ الأدنى للقوّة الغاشمة ستّةَ أرقامٍ بلا عدّاد.
            locked = _count_failure(user)
            AuditLog.log(
                user=user,
                action="mfa_failed",
                model_name="CustomUser",
                object_id=user.pk,
                object_repr=f"رمز تحقّق خاطئ — {user.full_name}",
                changes={"locked": locked},
                request=request,
            )
            if locked:
                for key in ("pending_2fa_user", "pending_identifier_kind", "pending_2fa_backend"):
                    request.session.pop(key, None)
                messages.error(
                    request,
                    f"تم قفل الحساب لمدة {LOCK_MINUTES} دقيقة بسبب المحاولات المتكررة.",
                )
                return redirect("login")
            messages.error(request, "رمز التحقق غير صحيح. حاول مجدداً.")

    return render(request, "auth/verify_2fa.html", {"user": user})


@login_required
@ratelimit(key="user", rate="3/m", method="POST", block=True)
def setup_2fa(request):
    """إعداد المصادقة الثنائية — توليد QR وتفعيل TOTP للمدير والنواب."""
    user = request.user

    if not requires_two_factor(user):
        messages.info(request, "المصادقة الثنائية للكادر — لا للطلبة وأولياء الأمور.")
        return redirect("dashboard")

    raw_secret = usable_totp_secret(user)
    if raw_secret is None:
        # لا سرَّ، أو سرٌّ لا يُقرأ بمفتاح هذه البيئة — يُولَّد من جديد. ومن كان مفعِّلاً
        # بسرٍّ غيرِ مقروءٍ فقد صار محبوساً أصلاً: يُعاد إعدادُه لا انتظارُ رمزٍ لن يأتي.
        from core.models import encrypt_field

        if user.totp_secret:
            logger.warning("TOTP secret unreadable for user %s — regenerated at setup", user.pk)
            if user.totp_enabled:
                messages.warning(request, "تعذّر قراءة سرّ المصادقة السابق — أُعيد الإعداد من جديد.")
        raw_secret = pyotp.random_base32()
        user.totp_secret = encrypt_field(raw_secret) or raw_secret
        user.totp_enabled = False
        user.save(update_fields=["totp_secret", "totp_enabled"])

    totp = pyotp.TOTP(raw_secret)
    otp_uri = totp.provisioning_uri(name=user.national_id, issuer_name="SchoolOS")

    qr = qrcode.QRCode(box_size=6, border=2)
    qr.add_data(otp_uri)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buf = BytesIO()
    img.save(buf, format="PNG")
    qr_b64 = base64.b64encode(buf.getvalue()).decode()

    if request.method == "POST":
        code = request.POST.get("code", "").strip().replace(" ", "")
        if totp.verify(code, valid_window=1):
            user.totp_enabled = True
            user.save(update_fields=["totp_enabled"])
            # أثبت الرمزَ الآن — وإلّا أغلق MfaSessionMiddleware جلستَه لحظةَ التفعيل.
            mark_verified(request)
            messages.success(request, "✅ تم تفعيل المصادقة الثنائية بنجاح!")
            return redirect("dashboard")
        else:
            messages.error(request, "رمز التحقق غير صحيح.")

    return render(
        request,
        "auth/setup_2fa.html",
        {
            "qr_b64": qr_b64,
            "secret": raw_secret,
            "totp_enabled": user.totp_enabled,
        },
    )


@login_required
@ratelimit(key="user", rate="3/m", method="POST", block=True)
def disable_2fa(request):
    """تعطيل المصادقة الثنائية بعد التحقق من الرمز الحالي."""
    if request.method == "POST":
        code = request.POST.get("code", "").strip()
        user = request.user
        _raw = usable_totp_secret(user)
        if _raw:
            totp = pyotp.TOTP(_raw)
            if totp.verify(code, valid_window=1):
                user.totp_enabled = False
                user.totp_secret = ""
                user.save(update_fields=["totp_enabled", "totp_secret"])
                messages.success(request, "تم إيقاف المصادقة الثنائية.")
                return redirect("dashboard")
            else:
                messages.error(request, "رمز التحقق غير صحيح.")
    return render(request, "auth/disable_2fa.html")


@login_required
@ratelimit(key="user", rate="5/m", method="POST", block=True)
def force_change_password(request):
    """إجبار المستخدم على تغيير كلمة المرور المؤقتة عند أول دخول."""
    if not request.user.must_change_password:
        return redirect("dashboard")

    if request.method == "POST":
        pw1 = request.POST.get("password1", "")
        pw2 = request.POST.get("password2", "")

        errors = []
        if pw1 != pw2:
            errors.append("كلمتا المرور غير متطابقتين.")
        else:
            # ✅ v5.1.1: استخدام Django validators بدل التحقق اليدوي
            from django.contrib.auth.password_validation import validate_password
            from django.core.exceptions import ValidationError as DjangoValidationError

            try:
                validate_password(pw1, user=request.user)
            except DjangoValidationError as e:
                errors.extend(e.messages)

        if errors:
            for e in errors:
                messages.error(request, e)
        else:
            user = request.user
            user.set_password(pw1)
            user.must_change_password = False
            user.last_password_change = timezone.now()
            user.save(update_fields=["password", "must_change_password", "last_password_change"])
            from django.contrib.auth import update_session_auth_hash

            update_session_auth_hash(request, user)
            messages.success(request, "✅ تم تغيير كلمة المرور بنجاح!")

            if requires_two_factor(user) and not user.totp_enabled:
                return redirect("setup_2fa")

            return redirect("dashboard")

    return render(request, "auth/force_change_password.html")


@login_required
@ratelimit(key="user", rate="5/m", method="POST", block=True)
def change_password(request):
    """تغييرُ كلمة المرور بالأصول — لكلّ مستخدم، من قائمته.

    الحاليّةُ تُطلب قبل الجديدة: جلسةٌ مفتوحةٌ على جهازٍ مشترك لا تكفي لتبديل
    الكلمة. والجديدةُ تمرّ بمدقّقات المنصّة نفسِها، ويُعاد تاريخُ التدوير من
    الصفر، وتبقى الجلسةُ قائمةً بلا خروج.
    """
    if request.method == "POST":
        current = request.POST.get("current_password", "")
        pw1 = request.POST.get("password1", "")
        pw2 = request.POST.get("password2", "")

        errors = []
        if not request.user.check_password(current):
            errors.append("كلمة المرور الحالية غير صحيحة.")
        elif pw1 != pw2:
            errors.append("كلمتا المرور غير متطابقتين.")
        elif current == pw1:
            errors.append("كلمة المرور الجديدة يجب أن تختلف عن الحالية.")
        else:
            from django.contrib.auth.password_validation import validate_password
            from django.core.exceptions import ValidationError as DjangoValidationError

            try:
                validate_password(pw1, user=request.user)
            except DjangoValidationError as e:
                errors.extend(e.messages)

        if errors:
            for e in errors:
                messages.error(request, e)
        else:
            user = request.user
            user.set_password(pw1)
            user.must_change_password = False
            user.last_password_change = timezone.now()
            user.save(update_fields=["password", "must_change_password", "last_password_change"])
            from django.contrib.auth import update_session_auth_hash

            update_session_auth_hash(request, user)
            messages.success(request, "✅ تم تغيير كلمة المرور بنجاح.")
            return redirect("dashboard")

    return render(request, "auth/change_password.html")


@require_POST
def logout_view(request):
    """تسجيل الخروج الآمن — مسح الجلسة والتوجيه لصفحة الدخول.

    و`Clear-Site-Data: "cache"` يمحو ذاكرةَ المتصفّح لهذا الموقع: ما حُفظ من
    صفحاتٍ شخصيّة قبل `no-store` لا يبقى على جهازٍ مشترك بعد الخروج (P1-3).
    ولا `"storage"`: تمحو تفضيلاتِ المستخدم وتُلغي عاملَ الخدمة العامّ، والصفحاتُ
    لم تعد تُحفظ في ذاكرة العامل أصلاً.
    """
    logout(request)
    request.session.flush()
    response = redirect("login")
    response["Clear-Site-Data"] = '"cache"'
    return response

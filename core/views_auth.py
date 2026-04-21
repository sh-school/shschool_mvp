import base64
import logging
from datetime import timedelta
from io import BytesIO

import django.db
import pyotp
import qrcode
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

from core.models import CustomUser

logger = logging.getLogger(__name__)


def _axes_reset(request, national_id: str) -> None:
    """
    إعادة تعيين عداد axes بعد تسجيل الدخول الناجح.
    ✅ v5.4: يُكمّل AXES_RESET_ON_SUCCESS=True بإعادة تعيين صريحة مربوطة بـ national_id.
    """
    try:
        from axes.helpers import reset_request

        reset_request(request=request, username=national_id)
    except ImportError:
        pass  # axes غير مثبّت — لا مشكلة


def _safe_redirect(url, request, fallback="dashboard"):
    """تحقق من أن الـ redirect URL آمن — يمنع Open Redirect attacks."""
    if url and url_has_allowed_host_and_scheme(
        url, allowed_hosts={request.get_host()}, require_https=request.is_secure()
    ):
        return redirect(url)
    return redirect(fallback)


ROLES_REQUIRING_2FA = {"principal", "vice_admin", "vice_academic", "admin"}

# ── رسالة خطأ موحّدة — تمنع User Enumeration ──────────────────────
# لا تغيّر هذه الرسالة ولا تجعلها تختلف بحسب وجود المستخدم من عدمه
_AUTH_ERROR = "الرقم الشخصي أو كلمة المرور غير صحيحة"


@ratelimit(key="ip", rate="10/m", method="POST", block=True)
def login_view(request):
    """صفحة تسجيل الدخول — مع حماية من القوة الغاشمة وقفل الحساب."""
    if request.user.is_authenticated:
        return redirect("dashboard")

    if request.method == "POST":
        national_id = request.POST.get("national_id", "").strip()
        password = request.POST.get("password", "").strip()

        if not national_id or not password:
            messages.error(request, "يرجى إدخال الرقم الشخصي وكلمة المرور")
            return render(request, "auth/login.html")

        # ── التحقق من قفل الحساب (الرسالة هنا مقبولة لأن القفل يحدث بعد محاولات) ──
        try:
            u = CustomUser.objects.get(national_id=national_id)
            if u.locked_until and u.locked_until > timezone.now():
                remaining = int((u.locked_until - timezone.now()).total_seconds() // 60) + 1
                messages.error(request, f"الحساب مقفل. حاول بعد {remaining} دقيقة.")
                return render(request, "auth/login.html")
        except CustomUser.DoesNotExist:
            pass

        user = authenticate(request, national_id=national_id, password=password)

        if user:
            user.failed_login_attempts = 0
            user.locked_until = None
            user.save(update_fields=["failed_login_attempts", "locked_until"])
            # ✅ v5.4: إعادة تعيين عداد axes عند تسجيل الدخول الناجح
            _axes_reset(request, national_id)

            role = user.get_role()
            if user.totp_enabled and role in ROLES_REQUIRING_2FA:
                request.session["pending_2fa_user"] = str(user.id)
                return redirect("verify_2fa")

            login(request, user)

            if user.must_change_password:
                return redirect("force_change_password")

            return _safe_redirect(request.GET.get("next", ""), request)

        else:
            # ── إصلاح User Enumeration ────────────────────────────────────────
            # نزيد العداد بصمت إذا وُجد المستخدم، لكن نُظهر نفس الرسالة دائماً
            # سواء وُجد الرقم الشخصي أم لا — المهاجم لا يعرف الفرق
            try:
                with transaction.atomic():
                    updated = (
                        CustomUser.objects.filter(national_id=national_id)
                        .select_for_update()
                        .update(failed_login_attempts=F("failed_login_attempts") + 1)
                    )
                    if updated:
                        u = CustomUser.objects.get(national_id=national_id)
                        if u.failed_login_attempts >= 5:
                            u.locked_until = timezone.now() + timedelta(minutes=15)
                            u.save(update_fields=["locked_until"])
                            # رسالة القفل مقبولة — تظهر فقط بعد 5 محاولات
                            messages.error(
                                request, "تم قفل الحساب لمدة 15 دقيقة بسبب المحاولات المتكررة."
                            )
                            return render(request, "auth/login.html")
            except (django.db.DatabaseError, ValueError) as e:
                logger.exception("فشل تحديث عداد محاولات تسجيل الدخول الفاشلة: %s", e)
                pass

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
        from core.models import decrypt_field as _dfd

        _s = _dfd(user.totp_secret) or user.totp_secret
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
            login(request, user)
            if user.must_change_password:
                return redirect("force_change_password")
            return _safe_redirect(request.GET.get("next", ""), request)
        else:
            messages.error(request, "رمز التحقق غير صحيح. حاول مجدداً.")

    return render(request, "auth/verify_2fa.html", {"user": user})


@login_required
@ratelimit(key="user", rate="3/m", method="POST", block=True)
def setup_2fa(request):
    """إعداد المصادقة الثنائية — توليد QR وتفعيل TOTP للمدير والنواب."""
    user = request.user
    role = user.get_role()

    if role not in ROLES_REQUIRING_2FA and not user.is_superuser:
        messages.info(request, "المصادقة الثنائية متاحة للمدير والنواب فقط.")
        return redirect("dashboard")

    if not user.totp_secret:
        raw_secret = pyotp.random_base32()
        from core.models import encrypt_field

        user.totp_secret = encrypt_field(raw_secret) or raw_secret
        user.save(update_fields=["totp_secret"])

    from core.models import decrypt_field as _df

    raw_secret = _df(user.totp_secret) or user.totp_secret
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
        code = request.POST.get("code", "").strip()
        if totp.verify(code, valid_window=1):
            user.totp_enabled = True
            user.save(update_fields=["totp_enabled"])
            messages.success(request, "✅ تم تفعيل المصادقة الثنائية بنجاح!")
            return redirect("dashboard")
        else:
            messages.error(request, "رمز التحقق غير صحيح.")

    from core.models import decrypt_field

    return render(
        request,
        "auth/setup_2fa.html",
        {
            "qr_b64": qr_b64,
            "secret": (decrypt_field(user.totp_secret) or user.totp_secret)
            if user.totp_secret
            else "",
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
        if user.totp_secret:
            from core.models import decrypt_field

            _raw = decrypt_field(user.totp_secret) or user.totp_secret
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

            role = user.get_role()
            if role in ROLES_REQUIRING_2FA and not user.totp_enabled:
                return redirect("setup_2fa")

            return redirect("dashboard")

    return render(request, "auth/force_change_password.html")


@require_POST
def logout_view(request):
    """تسجيل الخروج الآمن — مسح الجلسة والتوجيه لصفحة الدخول"""
    logout(request)
    request.session.flush()
    return redirect("login")

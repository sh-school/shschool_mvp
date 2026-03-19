import pyotp, qrcode, base64
from io import BytesIO
from datetime import timedelta

from django.shortcuts   import render, redirect
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib     import messages
from django.utils       import timezone
from django.http        import JsonResponse
from django.views.decorators.http import require_POST
from django.db.models   import F
from django.db          import transaction
from core.models        import CustomUser

ROLES_REQUIRING_2FA = {"principal", "vice_admin", "vice_academic", "admin"}


def login_view(request):
    if request.user.is_authenticated:
        return redirect("dashboard")

    if request.method == "POST":
        national_id = request.POST.get("national_id", "").strip()
        password    = request.POST.get("password", "").strip()

        if not national_id or not password:
            messages.error(request, "يرجى إدخال الرقم الوطني وكلمة المرور")
            return render(request, "auth/login.html")

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

            role = user.get_role()
            if user.totp_enabled and role in ROLES_REQUIRING_2FA:
                request.session["pending_2fa_user"] = str(user.id)
                return redirect("verify_2fa")

            login(request, user)

            if user.must_change_password:
                return redirect("force_change_password")

            next_url = request.GET.get("next", "dashboard")
            return redirect(next_url)

        else:
            try:
                with transaction.atomic():
                    CustomUser.objects.filter(
                        national_id=national_id
                    ).update(
                        failed_login_attempts=F('failed_login_attempts') + 1
                    )
                    u = CustomUser.objects.get(national_id=national_id)
                    if u.failed_login_attempts >= 5:
                        u.locked_until = timezone.now() + timedelta(minutes=15)
                        u.save(update_fields=["locked_until"])
                        messages.error(request, "تم قفل الحساب لمدة 15 دقيقة بسبب المحاولات المتكررة.")
                    else:
                        remaining = 5 - u.failed_login_attempts
                        messages.error(request, f"بيانات غير صحيحة. {remaining} محاولة متبقية.")
            except CustomUser.DoesNotExist:
                messages.error(request, "الرقم الوطني أو كلمة المرور غير صحيحة")

    return render(request, "auth/login.html")


def verify_2fa(request):
    user_id = request.session.get("pending_2fa_user")
    if not user_id:
        return redirect("login")

    try:
        user = CustomUser.objects.get(id=user_id)
    except CustomUser.DoesNotExist:
        return redirect("login")

    if request.method == "POST":
        code = request.POST.get("code", "").strip().replace(" ", "")
        totp = pyotp.TOTP(user.totp_secret)
        if totp.verify(code, valid_window=1):
            del request.session["pending_2fa_user"]
            login(request, user)
            if user.must_change_password:
                return redirect("force_change_password")
            return redirect(request.GET.get("next", "dashboard"))
        else:
            messages.error(request, "رمز التحقق غير صحيح. حاول مجدداً.")

    return render(request, "auth/verify_2fa.html", {"user": user})


@login_required
def setup_2fa(request):
    user = request.user
    role = user.get_role()

    if role not in ROLES_REQUIRING_2FA and not user.is_superuser:
        messages.info(request, "المصادقة الثنائية متاحة للمدير والنواب فقط.")
        return redirect("dashboard")

    if not user.totp_secret:
        user.totp_secret = pyotp.random_base32()
        user.save(update_fields=["totp_secret"])

    totp    = pyotp.TOTP(user.totp_secret)
    otp_uri = totp.provisioning_uri(name=user.national_id, issuer_name="SchoolOS")

    qr = qrcode.QRCode(box_size=6, border=2)
    qr.add_data(otp_uri)
    qr.make(fit=True)
    img    = qr.make_image(fill_color="black", back_color="white")
    buf    = BytesIO()
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

    return render(request, "auth/setup_2fa.html", {
        "qr_b64":       qr_b64,
        "secret":       user.totp_secret,
        "totp_enabled": user.totp_enabled,
    })


@login_required
def disable_2fa(request):
    if request.method == "POST":
        code = request.POST.get("code", "").strip()
        user = request.user
        if user.totp_secret:
            totp = pyotp.TOTP(user.totp_secret)
            if totp.verify(code, valid_window=1):
                user.totp_enabled = False
                user.totp_secret  = ""
                user.save(update_fields=["totp_enabled", "totp_secret"])
                messages.success(request, "تم إيقاف المصادقة الثنائية.")
                return redirect("dashboard")
            else:
                messages.error(request, "رمز التحقق غير صحيح.")
    return render(request, "auth/disable_2fa.html")


@login_required
def force_change_password(request):
    if not request.user.must_change_password:
        return redirect("dashboard")

    if request.method == "POST":
        pw1 = request.POST.get("password1", "")
        pw2 = request.POST.get("password2", "")

        errors = []
        if pw1 != pw2:
            errors.append("كلمتا المرور غير متطابقتين.")
        if len(pw1) < 8:
            errors.append("كلمة المرور يجب أن تكون 8 أحرف على الأقل.")
        if pw1.isdigit():
            errors.append("لا يمكن أن تكون كلمة المرور أرقاماً فقط.")

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


@login_required
@require_POST
def logout_view(request):
    logout(request)
    return redirect("login")
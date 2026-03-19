from django.shortcuts import render, redirect
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib import messages


def login_view(request):
    if request.user.is_authenticated:
        return redirect("dashboard")

    if request.method == "POST":
        national_id = request.POST.get("national_id", "").strip()
        password    = request.POST.get("password", "").strip()

        if not national_id or not password:
            messages.error(request, "يرجى إدخال الرقم الوطني وكلمة المرور")
            return render(request, "auth/login.html")

        user = authenticate(request, national_id=national_id, password=password)
        if user:
            login(request, user)
            next_url = request.GET.get("next", "dashboard")
            return redirect(next_url)
        else:
            # زيادة عداد المحاولات — atomic لتجنب race condition
            try:
                from django.db.models import F
                from django.db import transaction
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


from django.views.decorators.http import require_POST

@login_required
@require_POST
def logout_view(request):
    logout(request)
    return redirect("login")
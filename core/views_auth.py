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
            messages.error(request, "الرقم الوطني أو كلمة المرور غير صحيحة")

    return render(request, "auth/login.html")


@login_required
def logout_view(request):
    logout(request)
    return redirect("login")

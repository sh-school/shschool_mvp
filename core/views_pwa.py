from django.shortcuts import render


def global_sw(request):
    return render(request, "pwa/sw_global.js", content_type="application/javascript; charset=utf-8")


def global_manifest(request):
    # استخدام active_membership المُخزَّن مؤقتاً بدلاً من query مباشرة
    role = ""
    if request.user.is_authenticated:
        m = request.user.active_membership
        role = m.role.name if m else ""

    response = render(
        request, "pwa/manifest_global.json", {"role": role}, content_type="application/json"
    )
    # منع التخزين المؤقت العام — الـ manifest يختلف حسب المستخدم
    response["Cache-Control"] = "private, no-cache, no-store, must-revalidate"
    response["Vary"] = "Cookie"
    return response


def offline_global(request):
    return render(request, "pwa/offline_global.html")

"""مسارات اختبار عدّاد أخطاء الخادم — تُفعَّل بـ`settings.ROOT_URLCONF` داخل الاختبار وحده."""

from django.http import HttpResponse, JsonResponse
from django.urls import path

SECRET = "9876543210"


def boom(request, pk):
    raise RuntimeError(f"سقط عند الرقم الشخصي {SECRET}")


def explicit_500(request):
    return JsonResponse({"error": "x"}, status=500)


def fine(request):
    return HttpResponse("ok")


def health_down(request):
    return HttpResponse("down", status=503)


urlpatterns = [
    path("boom/<int:pk>/", boom),
    path("explicit/", explicit_500),
    path("fine/", fine),
    path("health/down/", health_down),
]

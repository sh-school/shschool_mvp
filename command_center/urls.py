"""مسارا «مركز قيادة الجودة» — جذريّان قبل `admin.site.urls` (سابقةُ `admin/login/`) في `shschool/urls.py`.

كلُّ مسارٍ مغلَّفٌ بـ`admin.site.admin_view(developer_only(view))`: مجهولٌ أو غيرُ موظّفٍ يُحوَّل إلى الدخول،
وموظّفٌ غيرُ مطوّر 403. ولا حارسَ آليّاً تحت `/admin/` (يُستثنى من اختبار المسارات المحروسة)، فيحرس
`tests/test_command_center.py` كلَّ مسارٍ هنا بنفسه — أضِف مساراً جديداً عبر `_guarded` وحدَه.
"""

from __future__ import annotations

from collections.abc import Callable

from django.contrib import admin
from django.http import HttpResponse
from django.urls import path

from command_center import views
from core.developer_access import developer_only

app_name = "command_center"


def _guarded(view: Callable[..., HttpResponse]) -> Callable[..., HttpResponse]:
    return admin.site.admin_view(developer_only(view))


urlpatterns = [
    path("", _guarded(views.index), name="index"),
    path("snapshot/", _guarded(views.snapshot), name="snapshot"),
]

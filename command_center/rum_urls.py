"""مسارُ استقبال القياس الميدانيّ — `/rum/collect/` (انظر `rum_views.py`). لا فضاءَ أسماء: مسارٌ واحدٌ يعرفه `RUM_ENDPOINT`."""

from __future__ import annotations

from django.urls import path

from command_center import rum_views

urlpatterns = [
    path("collect/", rum_views.collect, name="rum_collect"),
]

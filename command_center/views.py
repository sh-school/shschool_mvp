"""عرضا «مركز قيادة الجودة»: الصفحةُ ولقطتُها — كلاهما قراءةُ cache فقط (عقدُ `contract.py`)."""

from __future__ import annotations

from django.contrib import admin
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import render

from command_center import contract


def index(request: HttpRequest) -> HttpResponse:
    """الصفحةُ: لوحاتٌ مرسومةٌ من اللقطة الحاليّة، ويُحدّثها `command_center.js` بالاستطلاع."""
    context = {
        **admin.site.each_context(request),
        "title": "مركز قيادة الجودة",
        "snapshot": contract.snapshot(),
        "schema": contract.SCHEMA_VERSION,
    }
    return render(request, "command_center/index.html", context)


def snapshot(request: HttpRequest) -> JsonResponse:
    """اللقطةُ JSON — يستطلعها السكربتُ كلَّ 15–60 ثانية؛ لا شيءَ يُحسب هنا."""
    return JsonResponse(contract.snapshot())

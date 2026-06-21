"""
core/views_media.py
خدمة الملفات المُخزَّنة في قاعدة البيانات (DatabaseStorage) — محمية بتسجيل الدخول.
"""

import mimetypes
from urllib.parse import quote

from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.shortcuts import get_object_or_404


@login_required
def serve_db_file(request, name):
    """يُعيد ملفاً مُخزَّناً في القاعدة. متاح للمستخدمين المُصادَقين فقط (PDPPL)."""
    from core.models import StoredFile

    sf = get_object_or_404(StoredFile, name=name)
    content_type = sf.content_type or mimetypes.guess_type(name)[0] or "application/octet-stream"
    response = HttpResponse(bytes(sf.content), content_type=content_type)
    filename = name.rsplit("/", 1)[-1]
    # RFC 5987 — يدعم أسماء الملفات العربية
    response["Content-Disposition"] = f"inline; filename*=UTF-8''{quote(filename)}"
    response["Content-Length"] = sf.size or len(bytes(sf.content))
    response["X-Content-Type-Options"] = "nosniff"
    return response

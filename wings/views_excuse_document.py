"""
wings/views_excuse_document.py — فتحُ مستند عذر الغياب عبر عرضٍ محروس (W-20261008-012، PDPPL).

المستندُ قد يكون تقريراً طبّياً: بيانٌ صحّيٌّ حسّاس. فلا يُفتح برابط `/media/` المباشر، بل من هنا:
قدرةٌ، ثمّ مدرسةُ العذر، ثمّ نطاقُ الجناح للمشرف، ثمّ سطرُ تدقيقٍ لكلّ فتح بلا اسم الملف ولا اسم الطالب.
"""

from __future__ import annotations

import mimetypes
import os

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.http import FileResponse, Http404, HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404

from core.audit_repr import masked_repr
from core.capabilities import has_capability
from core.models import AuditLog
from operations.models import AbsenceExcuse
from wings.scope import student_scope_for

#: النائبُ الإداريّ يرى أعذارَ المدرسة كلَّها؛ والمشرفُ أعذارَ طلبة جناحه وحدَهم.
WIDE = "wings.excuse_after_deadline"
WING = "wings.record_day"


@login_required
def excuse_document(request: HttpRequest, pk) -> HttpResponse:
    """يخدم مستندَ العذر مرفقاً — غيرُ المخوَّل 403، وعذرٌ من غير مدرسته أو جناحه 404 كغير الموجود."""
    user = request.user
    wide = has_capability(user, WIDE)
    if not (wide or has_capability(user, WING)):
        raise PermissionDenied
    excuse = get_object_or_404(AbsenceExcuse, pk=pk, school=request.school)
    if not excuse.document:
        raise Http404
    if not wide:
        student_scope_for(request).require_student(excuse.student_id)

    AuditLog.log(
        user=user,
        action="view",
        model_name="AbsenceExcuse",
        object_id=excuse.pk,
        object_repr=f"مستند عذر {masked_repr(excuse.student)}",
        changes={"event": "excuse_document_opened", "role": user.get_role()},  # type: ignore[union-attr]
        school=excuse.school,
        request=request,
    )

    ext = os.path.splitext(excuse.document.name)[1].lower() or ".bin"
    response = FileResponse(
        excuse.document.open("rb"),
        content_type=mimetypes.types_map.get(ext, "application/octet-stream"),
        as_attachment=True,
        filename=f"excuse-{str(excuse.pk)[:8]}{ext}",
    )
    response["X-Content-Type-Options"] = "nosniff"
    response["Cache-Control"] = "private, no-store"
    return response

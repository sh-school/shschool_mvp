"""تصديرُ الملف السلوكيّ للطالب Excel على عقد التصدير المركزيّ (W-20261109-006).

المحدِّدُ `export_tables.profile_rows` يقرأ مخالفاتِ الطالب كما يعرضها ملفُّه ويمنع من لا يبلغه نطاقُه (404 للمشرف خارج جناحه).
"""

from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse

from core.capabilities import capability_required
from core.exports.services import respond_export

from .export_tables import PROFILE_TABLE


@login_required
@capability_required("behavior.view")
def student_profile_xlsx(request: HttpRequest, student_id) -> HttpResponse:
    params = request.GET.copy()
    params["student"] = str(student_id)
    return respond_export(request, PROFILE_TABLE.kind, params=params)

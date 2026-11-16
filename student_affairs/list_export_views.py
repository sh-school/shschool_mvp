"""تصدير قائمة الطلبة Excel على عقد التصدير المركزيّ (W-20261109-013).

المعاملاتُ كلُّها (البحثُ والصفُّ والشعبةُ والحالةُ وحالةُ وليّ الأمر…) تصل المحدِّدَ `rows_for` كما وصلت الرابط،
فيخرج الملفُّ المعروضَ بعد الفلترة وبنطاق الدور لا السجلَّ كلَّه.
"""

from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse

from core.capabilities import capability_required
from core.exports.services import respond_export

from .export_builders import STUDENT_LIST_TABLE


@login_required
# حارسُ الشاشة نفسُه (`view`): من يقرأ القائمةَ يصدّر ما يقرؤه وبنطاقه وحدَه — والمشرفُ المقيَّدُ لجناحه.
@capability_required("student_affairs.view")
def student_list_xlsx(request: HttpRequest) -> HttpResponse:
    return respond_export(request, STUDENT_LIST_TABLE.kind, params=request.GET.copy())

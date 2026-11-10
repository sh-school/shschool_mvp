"""تصديرُ جداول الجناح Excel وPDF على عقد التصدير المركزيّ (W-20261109-007).

المعاملاتُ كلُّها (التاريخُ والصفُّ والجناحُ والبحثُ والأعمدةُ المخفيّة) تصل محدِّدَ الجدول كما وصلت الرابط؛ والقدرةُ يفحصها
`respond_export` من السجلّ — فلا يخرج ملفٌّ لمن لا تفتح له الشاشةُ.
"""

from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse

from core.exports.services import respond_export

from . import export_tables as tables


def _export(kind: str):
    @login_required
    def view(request: HttpRequest) -> HttpResponse:
        return respond_export(request, kind, params=request.GET.copy())

    view.__name__ = kind.replace(".", "_")
    return view


register_xlsx = _export(tables.REGISTER_TABLE.kind)
register_pdf = _export("wings.register_pdf")
ministry_xlsx = _export(tables.MINISTRY_TABLE.kind)
ministry_pdf = _export("wings.ministry_table_pdf")
exit_permits_xlsx = _export(tables.EXIT_PERMITS_TABLE.kind)
exit_permits_pdf = _export("wings.exit_permits_pdf")

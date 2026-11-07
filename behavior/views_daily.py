"""التقرير السلوكيّ اليوميّ — صفحةٌ بتاريخ يومٍ ومرشِّحَي الجناح والصفّ، وتصديرُها PDF وExcel.

الصفوفُ كلُّها من `selectors.daily_report` (مصدرٌ واحدٌ للشاشة والملفّين)، والتصديرُ خلفيٌّ عبر سجلّ التصدير
(`behavior.daily_pdf` و`behavior.daily_xlsx`) فيكتب العاملُ سطرَ التدقيق بعدد الصفوف بلا نصّ وصفٍ ولا اسم.
القدرةُ القائمةُ `behavior.statistics` بنطاقها — بلا قدرةٍ جديدة.
"""

from django.contrib.auth.decorators import login_required
from django.shortcuts import render

from core.capabilities import capability_required
from core.exports.services import respond_export

from .selectors import daily_report


@login_required
@capability_required("behavior.statistics")
def daily_report_page(request):
    """صفحةُ اليوم (الافتراضيُّ اليوم) بصفوفها ومرشِّحاتها."""
    data = daily_report(request.school, request.user, request.GET)
    query = request.GET.copy()
    query["date"] = f"{data['day']:%Y-%m-%d}"
    return render(
        request,
        "behavior/daily_report.html",
        {
            **data,
            "export_query": query.urlencode(),
            "total": len(data["rows"]),
        },
    )


@login_required
@capability_required("behavior.statistics")
def daily_report_pdf(request):
    return respond_export(request, "behavior.daily_pdf")


@login_required
@capability_required("behavior.statistics")
def daily_report_xlsx(request):
    return respond_export(request, "behavior.daily_xlsx")

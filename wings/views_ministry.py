"""ملخّصُ الحصّتين الأولى والثانية للرفع في نظام الوزارة — معاينةً أو PDF أو Excel.

الصلاحيّةُ صلاحيّةُ الرصد (`wings.record_day`) والنطاقُ نطاقُ الطلبة نفسُه: المشرفُ لطلبة جناحه، وحاصرُ
الغياب العامّ والقيادةُ للمدرسة كلِّها. والتصديرُ يُدقَّق كأيّ مصدِّر، بلا رقمٍ شخصيّ.
"""

from django.contrib.auth.decorators import login_required
from django.utils import timezone

from core.capabilities import capability_required

from .ministry_response import respond
from .ministry_selectors import summary_for_request
from .views import _day
from .views_register import _format, _orientation


@login_required
@capability_required("wings.record_day")
def ministry_report(request):
    """غابوا الأولى والثانية — بالشعبة والصفّ والمدرسة، وأسماءُ من يُرفعون."""
    day = _day(request.GET.get("date"), timezone.localdate())
    summary, bound = summary_for_request(request, day)
    return respond(
        request,
        request.school,
        summary,
        fmt=_format(request),
        orient=_orientation(request),
        bound=bound,
    )

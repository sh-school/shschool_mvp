"""ملخّصُ الحصّتين الأولى والثانية للرفع في نظام الوزارة — شاشةَ منصّةٍ أو PDF أو Excel.

الصلاحيّةُ صلاحيّةُ الرصد (`wings.record_day`) والنطاقُ نطاقُ الطلبة نفسُه: المشرفُ لطلبة جناحه، وحاصرُ
الغياب العامّ والقيادةُ للمدرسة كلِّها. والتصديرُ يُدقَّق كأيّ مصدِّر، بلا رقمٍ شخصيّ. والترشيحُ (الصفّ والبحث) يسري على الشاشة والملفّ معاً.
"""

from django.contrib.auth.decorators import login_required
from django.utils import timezone

from core.capabilities import capability_required

from .ministry_response import respond
from .ministry_selectors import ministry_view
from .views_register import _format, _orientation


@login_required
@capability_required("wings.record_day")
def ministry_report(request):
    """غابوا الأولى والثانية — بالشعبة والصفّ والمدرسة، وأسماءُ من يُرفعون."""
    # المحدِّدُ نفسُه الذي يقرأ به جدولُ التصدير (`ministry_rows`): نطاقُ الدور ثمّ الترشيحُ كاملاً.
    view = ministry_view(request.user, request.school, request.GET, timezone.localdate())
    return respond(
        request,
        request.school,
        view.summary,
        fmt=_format(request),
        orient=_orientation(request),
        bound=view.bound,
        screen={
            "grades": view.grades,
            "grade": view.grade,
            "q": view.q,
            "wings": view.wings,
            "wing": view.wing,
        },
    )

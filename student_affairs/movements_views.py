"""شاشةُ تحرّكات الطلبة الزمنيّة: قيدٌ ونقلٌ وانسحابٌ وتغييرُ شعبة (W-20261106-016).

وحدةٌ مستقلّة عن `views.py` حفاظاً على سقف حجمه. غيرُ `student_movements` هناك التي تقرأ
خروجَ الطالب أثناء الحصّة (`ClassExit`)؛ هذه تقرأ تاريخَ القيد نفسِه من `selectors.enrolment_movements`.
الحارسُ `student_affairs.transfers` — منسّقُ شؤون الطلبة والإدارة بأدوارهم الحاليّة.
"""

from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.shortcuts import render

from core.academic_calendar import academic_year_for
from core.capabilities import capability_required
from core.exports.services import respond_export

from .selectors import MOVEMENT_KINDS, enrolment_movements, movement_filters, year_sections

# حركاتٌ في الصفحة الواحدة — التصديرُ لا يتقيّد بها، فيأتي كلُّ ما يطابق المرشِّحات.
MOVEMENTS_PAGE_SIZE = 50


@login_required
@capability_required("student_affairs.transfers")
def enrolment_movements_list(request):
    """قائمةُ تحرّكات الطلبة بنطاق المدرسة والعام، بترشيحٍ بالشعبة والفترة والنوع، مقسّمةً صفحات."""
    school = request.school
    year = academic_year_for(request)
    filters = movement_filters(request.GET)
    page_obj = Paginator(
        enrolment_movements(school, year, **filters), MOVEMENTS_PAGE_SIZE
    ).get_page(request.GET.get("page"))
    return render(
        request,
        "student_affairs/movements.html",
        {
            "page_obj": page_obj,
            "kinds": MOVEMENT_KINDS,
            "sections": year_sections(school, year),
            "kind": filters["kind"],
            "section_filter": filters["class_group_id"],
            "date_from": request.GET.get("from", ""),
            "date_to": request.GET.get("to", ""),
            "year": year,
        },
    )


@login_required
@capability_required("student_affairs.transfers")
def enrolment_movements_export(request):
    """تصدير القائمة نفسِها إلى Excel بالمرشِّحات نفسِها — مهمّةٌ خلفيّةٌ (`student_affairs.movements_xlsx`).

    البنّاءُ في `student_affairs.export_builders` والآليّةُ مركزيّةٌ (`core.exports`).
    """
    return respond_export(request, "student_affairs.movements_xlsx")

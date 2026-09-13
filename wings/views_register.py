"""تصديرُ كشف الحصص وطباعتُه — كشفُ الشعبة وكشفُ الجناح.

ثلاثةُ مخارجَ من بياناتٍ واحدة (`wings/register.py`)، بـ`?format=`:

- `html` — نسخةٌ ورقيّةٌ في المتصفّح، و`?print=1` يفتح نافذةَ الطباعة وحدَها.
- `pdf`  — `render_pdf` تنزيلاً، من القالب نفسِه.
- `xlsx` — ورقةٌ محميّةٌ للقراءة، ولكشف الجناح ورقةُ ملخّصٍ ثمّ ورقةٌ لكلّ شعبة.

والصلاحيّةُ صلاحيّةُ الرصد نفسُها: المشرفُ لجناحه، والقيادةُ للأجنحة كلِّها.
"""

from django.contrib.auth.decorators import login_required
from django.http import Http404
from django.shortcuts import render
from django.template.loader import render_to_string
from django.utils import timezone

from core.academic_calendar import academic_year_for_school
from core.capabilities import capability_required
from core.export_utils import generate_export_filename, get_export_context
from core.pdf_utils import render_pdf
from reports.services import ExcelService

from .register import footer_lines, section_register, wing_register
from .register_excel import section_workbook, wing_workbook
from .services import wings_of
from .views import _day, _own_class

FORMATS = ("html", "pdf", "xlsx")


def _format(request) -> str:
    wanted = request.GET.get("format", "html")
    return wanted if wanted in FORMATS else "html"


def _orientation(request) -> str:
    """أفقيٌّ افتراضاً، وعموديٌّ بالاختيار — صفحةٌ واحدةٌ لكلّ فصل (قرارُ 2026-09-13)."""
    return "portrait" if request.GET.get("orient") == "portrait" else "landscape"


def _slug(text: str) -> str:
    """جزءُ اسم الملفّ: «11.5» لا تُقرأ نقطتُها امتداداً."""
    return "".join(ch if ch.isalnum() else "-" for ch in text)


def _respond(request, *, fmt, title, slug, context, workbook):
    ctx = get_export_context(request, title)
    ctx["school"] = request.user.get_school()
    ctx["orient"] = _orientation(request)
    ctx["footer"] = footer_lines(ctx["school"])
    if fmt == "xlsx":
        return ExcelService.to_response(
            workbook(ctx["school_name"], ctx["exported_by"], ctx["orient"], ctx["footer"]),
            generate_export_filename("wings", slug, "xlsx"),
        )
    ctx.update(context)
    if fmt == "pdf":
        html = render_to_string("wings/register_pdf.html", ctx, request=request)
        return render_pdf(html, generate_export_filename("wings", slug, "pdf"), as_attachment=True)
    ctx["for_screen"] = True
    ctx["autoprint"] = request.GET.get("print") == "1"
    return render(request, "wings/register_pdf.html", ctx)


@login_required
@capability_required("wings.record_day")
def section_register_export(request, class_id):
    """كشفُ شعبةٍ لليوم — طباعةً أو PDF أو Excel."""
    _school, klass = _own_class(request, class_id)
    day = _day(request.GET.get("date"), timezone.localdate())
    register = section_register(klass, day)
    return _respond(
        request,
        fmt=_format(request),
        title=register.title,
        slug=f"register_{_slug(klass.short_code)}",
        context={"section_register": register},
        workbook=lambda school_name, by, orient, footer: section_workbook(
            register, school_name, by, orient, footer
        ),
    )


@login_required
@capability_required("wings.record_day")
def wing_register_export(request, code):
    """كشفُ الجناح كاملاً لليوم — ملخّصُ الشُّعب ثمّ كشفُ كلّ شعبة."""
    school = request.user.get_school()
    year = academic_year_for_school(school)
    wing = next((w for w in wings_of(request.user, school, year) if w.code == code), None)
    if wing is None:
        raise Http404("ليس من أجنحتك")
    day = _day(request.GET.get("date"), timezone.localdate())
    register = wing_register(wing, day)
    return _respond(
        request,
        fmt=_format(request),
        title=register.title,
        slug=f"wing_register_{_slug(wing.code)}",
        context={"wing_register": register},
        workbook=lambda school_name, by, orient, footer: wing_workbook(
            register, school_name, by, orient, footer
        ),
    )

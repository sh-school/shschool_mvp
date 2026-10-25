"""التقريرُ الشهريّ للعيادة Excel — عدديٌّ بحتٌ بلا أسماءَ ولا أرقامَ شخصيّةٍ ولا نصٍّ حرّ (W-20261020-032).

يقوم مقامَ الملفّ اليدويّ: ورقةُ «السجل» صفوفُها الخدماتُ بترتيب `choices.SERVICES` وأعمدتُها قطريّ/غيرُ قطريّ/المجموع،
وورقةُ «اللوحة» ملخّصاتُ المجموعة وحالةِ الخروج والشكوى والحصّة. الحقولُ المشفَّرة (reason/symptoms/treatment) لا تُقرأ هنا أبداً،
والطالبُ لا يُستعلَم عنه إلا بجنسيّته لغرض العدّ فقط.

الإخفاءُ (الحدُّ الأدنى للخلايا): عددٌ من 1 إلى 4 في أعمدة التفصيل يُعرض «<5» منعاً لتعريف طالبٍ بعينه؛ وعمودُ المجموع للخدمة دقيقٌ.
الجنسيةُ الفارغةُ تُحسب «غيرَ قطريّ» (لا قطريّ مؤكَّد)، وقد دُوّن ذلك في الورقة.
"""

from __future__ import annotations

import calendar
import datetime as dt
from collections import Counter
from typing import Any

from django.utils import timezone

from . import choices

SUPPRESS_BELOW = 5
SUPPRESSED = "<5"
XLSX_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
_QATARI_PREFIX = "قطر"


def _shown(n: int) -> int | str:
    """عددٌ للعرض: الصفرُ يبقى صفراً، و1–4 تُخفى."""
    return SUPPRESSED if 0 < n < SUPPRESS_BELOW else n


def is_qatari(nationality: str) -> bool:
    return (nationality or "").strip().startswith(_QATARI_PREFIX)


def month_bounds(year: int, month: int) -> tuple[dt.datetime, dt.datetime]:
    tz = timezone.get_current_timezone()
    start = dt.datetime(year, month, 1, tzinfo=tz)
    last = calendar.monthrange(year, month)[1]
    end = dt.datetime(year, month, last, tzinfo=tz) + dt.timedelta(days=1)
    return start, end


def monthly_counts(school: Any, year: int, month: int) -> dict[str, Any]:
    """تجميعٌ خامٌّ للشهر (أعدادٌ صحيحة، بلا إخفاء). النطاقُ بالمدرسة وتاريخ الزيارة."""
    from .models import ClinicVisit

    start, end = month_bounds(year, month)
    rows = ClinicVisit.objects.filter(
        school=school, visit_date__gte=start, visit_date__lt=end
    ).values_list(
        "service_code", "outcome", "complaint_code", "period_number", "student__nationality"
    )
    by_service: dict[str, Counter] = {}
    outcomes: Counter = Counter()
    complaints: Counter = Counter()
    periods: Counter = Counter()
    uncoded = 0
    total = 0
    for service, outcome, complaint, period, nat in rows:
        total += 1
        if choices.is_valid_service(service):
            by_service.setdefault(service, Counter())["qa" if is_qatari(nat) else "non"] += 1
        else:
            uncoded += 1
        if outcome:
            outcomes[outcome] += 1
        if complaint:
            complaints[complaint] += 1
        if period:
            periods[period] += 1
    return {
        "total": total,
        "uncoded": uncoded,
        "by_service": by_service,
        "outcomes": outcomes,
        "complaints": complaints,
        "periods": periods,
    }


def service_rows(counts: dict[str, Any]) -> list[tuple[str, str, Any, Any, Any]]:
    """(المجموعة، الخدمة، قطريّ، غيرُ قطريّ، المجموع) بترتيب `SERVICES`؛ والمجموعُ دون 5 يُخفى (قرار المالك 2026-10-25)."""
    group_label = dict(choices.SERVICE_GROUPS)
    out = []
    for code, label, group in choices.SERVICES:
        c = counts["by_service"].get(code, Counter())
        qa, non = c["qa"], c["non"]
        out.append((group_label[group], label, _shown(qa), _shown(non), _shown(qa + non)))
    return out


def dashboard_rows(counts: dict[str, Any]) -> list[tuple[str, str, Any]]:
    """(القسم، البند، العدد) لمجموعات الخدمة وحالات الخروج والشكاوى والحصص."""
    group_label = dict(choices.SERVICE_GROUPS)
    per_group: Counter = Counter()
    for code, c in counts["by_service"].items():
        per_group[choices.group_of_service(code)] += c["qa"] + c["non"]
    out: list[tuple[str, str, Any]] = [
        ("مجموعة الخدمة", group_label[g], _shown(per_group[g])) for g, _ in choices.SERVICE_GROUPS
    ]
    out += [
        ("حالة الخروج", label, _shown(counts["outcomes"][code]))
        for code, label in choices.OUTCOME_CHOICES
    ]
    out += [
        ("الشكوى", label, _shown(counts["complaints"][code]))
        for code, label in choices.COMPLAINT_CHOICES
    ]
    out += [("الحصة", f"الحصة {p}", _shown(n)) for p, n in sorted(counts["periods"].items())]
    return out


def build_workbook(school: Any, year: int, month: int) -> bytes:
    from io import BytesIO

    from core.export_utils import apply_print_footer
    from reports.services import ExcelService

    counts = monthly_counts(school, year, month)
    wb, ws, styles = ExcelService._make_workbook("السجل")
    title = f"التقرير الشهري للعيادة — {month:02d}/{year}"
    school_name = getattr(school, "name", "") or ""

    cols = [("المجموعة", 20), ("الخدمة", 28), ("قطري", 12), ("غير قطري", 12), ("المجموع", 12)]
    ExcelService._add_professional_header(ws, school_name, title, str(year), len(cols))
    ExcelService._add_header_row(ws, styles, 4, cols)
    r = 5
    for i, row in enumerate(service_rows(counts)):
        for j, v in enumerate(row, start=1):
            ws.cell(row=r, column=j, value=v)
        ExcelService._style_data_row(ws, styles, r, len(cols), is_alt=bool(i % 2))
        r += 1
    ws.cell(
        row=r + 1,
        column=1,
        value=f"إجمالي الزيارات: {counts['total']} — منها غيرُ مرمَّزة: {counts['uncoded']}",
    )
    ws.cell(
        row=r + 2,
        column=1,
        value=f"الأعدادُ من 1 إلى {SUPPRESS_BELOW - 1} تظهر «{SUPPRESSED}»؛ والجنسيةُ الفارغة تُعدّ غيرَ قطريّ.",
    )
    ws.freeze_panes = "A5"

    ws2 = wb.create_sheet("اللوحة")
    ws2.sheet_view.rightToLeft = True
    cols2 = [("القسم", 20), ("البند", 30), ("العدد", 12)]
    ExcelService._add_professional_header(ws2, school_name, title, str(year), len(cols2))
    ExcelService._add_header_row(ws2, styles, 4, cols2)
    r = 5
    for i, row in enumerate(dashboard_rows(counts)):
        for j, v in enumerate(row, start=1):
            ws2.cell(row=r, column=j, value=v)
        ExcelService._style_data_row(ws2, styles, r, len(cols2), is_alt=bool(i % 2))
        r += 1
    ws2.freeze_panes = "A5"

    apply_print_footer(wb, school)  # رؤيةُ الوزارة في ذيل الطباعة (قرار المالك 2026-09-27)
    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()


def build_monthly_export(school: Any, user: Any, params: Any):
    """بنّاءُ سجلّ التصدير المركزيّ: `params` فيه `year` و`month` (الافتراضيّ الشهرُ الماضي)."""
    from core.exports.registry import ExportResult

    year, month = resolve_month(params)
    content = build_workbook(school, year, month)
    return ExportResult(
        content=content,
        content_type=XLSX_TYPE,
        filename=f"clinic_monthly_{year}{month:02d}.xlsx",
        rows=monthly_counts(school, year, month)["total"],
        object_id=f"{year}-{month:02d}",
    )


MONTHS_AR = "يناير فبراير مارس أبريل مايو يونيو يوليو أغسطس سبتمبر أكتوبر نوفمبر ديسمبر".split()


def resolve_month(params: Any) -> tuple[int, int]:
    """الشهرُ من `params` وإلا الشهرُ الماضي."""
    today = timezone.localdate()
    prev = today.replace(day=1) - dt.timedelta(days=1)
    try:
        year = int(params.get("year") or prev.year)
        month = int(params.get("month") or prev.month)
        if not 1 <= month <= 12:
            raise ValueError
    except (TypeError, ValueError):
        return prev.year, prev.month
    return year, month


def build_monthly_pdf(school: Any, user: Any, params: Any):
    """التقريرُ الشهريّ PDF بالهويّة الموحَّدة (W-20261020-037): غلافٌ وجدولُ الخدمات وتذييلُ سرّيّةٍ وتوقيعُ اعتماد المدير."""
    from django.template.loader import render_to_string

    from core.export_utils import get_export_context_for
    from core.exports.registry import ExportResult
    from core.pdf_utils import render_pdf_bytes

    year, month = resolve_month(params)
    counts = monthly_counts(school, year, month)
    month_label = f"{MONTHS_AR[month - 1]} {year}"
    ctx = get_export_context_for(user, f"التقرير الشهري للعيادة — {month_label}")
    html = render_to_string(
        "reports/clinic_monthly.html",
        {
            **ctx,
            "school": school,
            "month_label": month_label,
            "total": counts["total"],
            "uncoded": counts["uncoded"],
            "service_rows": service_rows(counts),
            "dashboard_rows": dashboard_rows(counts),
            "for_pdf": True,
        },
    )
    return ExportResult(
        content=render_pdf_bytes(html, paper_size="A4"),
        content_type="application/pdf",
        filename=f"clinic_monthly_{year}{month:02d}.pdf",
        rows=counts["total"],
        object_id=f"{year}-{month:02d}",
    )

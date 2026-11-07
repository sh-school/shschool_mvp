"""قالب فوتر Playwright — مفصولٌ عن core/pdf_utils.py لبقاء الملفّ تحت حدّ الحجم."""

from core import brand


def playwright_footer_template(today: str) -> str:
    """فوتر احترافي — يعمل على كل صفحة في Playwright"""
    return f"""
<style>
* {{ margin:0; padding:0; box-sizing:border-box; }}
.pf {{
    font-family: 'Tajawal', 'Amiri', Arial, sans-serif;
    direction:   rtl;
    width:       100%;
    padding:     5px 26px;
    display:     flex;
    justify-content: space-between;
    align-items: center;
    border-top:  1px solid {brand.BORDER};
    background:  {brand.SURFACE};
    -webkit-print-color-adjust: exact;
    print-color-adjust: exact;
    font-size:   8px;
    color:       {brand.TEXT_MUTED};
}}
.pf-brand {{ color: {brand.BORDER_STRONG}; font-size: 7.5px; letter-spacing: 0.5px; }}
.pf-pages {{ color: {brand.TEXT_SECONDARY}; direction: ltr; font-size: 8.5px; }}
.pf-date  {{ color: {brand.TEXT_MUTED}; font-size: 7.5px; direction: ltr; }}
</style>
<div class="pf">
    <span class="pf-brand">SchoolOS</span>
    <span class="pf-pages">
        صفحة <span class="pageNumber"></span> / <span class="totalPages"></span>
    </span>
    <span class="pf-date">{today}</span>
</div>
"""

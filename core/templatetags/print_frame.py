"""وسومُ الإطار المطبوع المركزيّ — `{% print_frame_css %}` و`{% print_frame_header %}` و`{% print_frame_footer %}`.

قوالبُ PDF تستهلك هذه الوسومَ بدل أن تكتب ترويستَها وتذييلَها (المواصفة `docs/design/print_fit_spec.md` §٥). الأرقامُ من `core/print_frame.py`
والألوانُ من `brand_color` في قوالب المكوّن (لا لونَ في بايثون)، والتذييلُ صفٌّ واحدٌ بعناصرَ تسعها الأولويّاتُ (`footer_plan`).
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any

from django import template
from django.template.loader import render_to_string
from django.utils import timezone

from core import print_frame as pf

register = template.Library()

MINISTRY = "وزارة التربية والتعليم والتعليم العالي — دولة قطر"

_TAGS = re.compile(r"<[^>]+>")


def _vision_text(school: Any) -> str:
    """نصُّ رؤية الوزارة كما تكتبه الجزئيّةُ الموحَّدة (`components/ministry_vision.html`) — مصدرٌ واحد."""
    return _TAGS.sub(
        "", render_to_string("components/ministry_vision.html", {"school": school})
    ).strip()


def _contact(school: Any) -> str:
    parts = [
        f"هاتف: {school.phone}" if getattr(school, "phone", "") else "",
        getattr(school, "email", "") or "",
        f"{school.city}، قطر" if getattr(school, "city", "") else "",
    ]
    return " · ".join(p for p in parts if p)


@register.simple_tag
def print_frame_css(paper: str, orient: str) -> str:
    """كتلةُ `<style>` للصفحة والإطار: `@page` بحجم الورق والهوامش ومربّعَي الترويسة والتذييل، وأنماطُهما بألوان الهويّة."""
    return render_to_string(
        "components/print/frame_css.html",
        {"fr": pf.frame(paper, orient), "footer_pt": pf.FOOTER_PT},
    )


@register.inclusion_tag("components/print/frame_header.html")
def print_frame_header(
    paper: str, orient: str, school: Any, title: str, subtitle: str = "", for_pdf: bool = False
) -> dict[str, Any]:
    """الترويسةُ الكاملة: شعارٌ فوزارةٌ فمدرسةٌ فعنوانُ الوثيقة فسطرُ السنة/الأسبوع، وسطرُ الرؤية حيث ينقلها الإطارُ إليها (D1)."""
    fr = pf.frame(paper, orient)
    return {
        "school": school,
        "title": title,
        "subtitle": subtitle,
        "for_pdf": for_pdf,
        "ministry": MINISTRY,
        "vision": _vision_text(school) if fr.vision_in_header else "",
    }


@register.inclusion_tag("components/print/frame_footer.html")
def print_frame_footer(
    paper: str, orient: str, school: Any, printed_at: datetime | None = None, stats: str = ""
) -> dict[str, Any]:
    """صفٌّ واحدٌ ثابتُ الارتفاع: المدرسةُ وص/ص وتاريخُ الطباعة (ملزِمة) ثمّ إحصاءُ المستهلك (`stats`، اختياريٌّ) فالرؤيةُ والوزارةُ والاتّصالُ وSchoolOS-SAMM ما وَسِعها الصفّ.

    ما لا يسع يسقط بالأولويّة بلا قصٍّ؛ والملزِمُ الذي لا يسع (اسمُ مدرسةٍ طويلٌ جدّاً) يُظهر `overflow` في السياق ليقرّر المستهلكُ لا أن يُقصّ صامتاً.
    و`stats` نصٌّ جاهزٌ يمرّره المستهلكُ (مثلاً «المعلّمون: 72 · الشُّعب: 25 · الحصص: 869 من 869 مخطَّطة») — يُعامَل كنصٍّ حرٍّ عاديٍّ (لا وسومَ HTML فيه) يمرّ بالتهريب
    التلقائيّ لقوالب Django كسائر عناصر التذييل؛ لا حاجةَ لتهريبٍ إضافيٍّ من المستهلك.
    """
    fr = pf.frame(paper, orient)
    vision = _vision_text(school)
    contact = _contact(school)
    when = timezone.localtime(printed_at or timezone.now())
    date_text = when.strftime("%Y/%m/%d %H:%M")
    plan = pf.footer_plan(
        fr,
        school=school.name,
        vision=vision,
        ministry=MINISTRY,
        contact=contact,
        stats=stats,
        date_text=date_text,
    )
    # التاريخُ بين عازلَي اتّجاه: مولّدُ PDF لا يقرأ `unicode-bidi` فيقلب «2026/09/26 22:40» في سطرٍ عربيّ.
    texts = {
        "school": school.name,
        "date": f"تاريخ الطباعة: ⁦{date_text}⁩",
        "stats": stats,
        "vision": vision,
        "ministry": MINISTRY,
        "contact": contact,
    }
    return {
        "items": [{"key": k, "text": texts.get(k, "")} for k in plan.items],
        "overflow": not plan.fits,
        "footer_pt": plan.font_pt,
        "date_text": date_text,
    }

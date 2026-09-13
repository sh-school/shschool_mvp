"""مكوّناتُ الواجهة — مصدرٌ واحدٌ لكلّ شكلٍ تتكرّر فيه البطاقة.

كانت كلُّ صفحةٍ تكتب بطاقاتِها بيدها، فصار للمنصّة خمسةُ أنظمةٍ لبطاقة الرقم
وخمسةُ أشكالٍ للترويسة (مراجعة 2026-09-13، `tests/design_ratchet.py`). فالصفحةُ
هنا تمرّر **البيانات** والوسمُ يملك **الشكل**: يُغيَّر في موضعٍ واحد، ويرفض ما
يخالف القواعد بدل أن يرسمه:

    {% load ui %}
    {% page_header "أجنحة المدرسة" subtitle="طابقان · 5 أجنحة" icon="layers" %}
      <a class="btn-secondary btn-sm" href="…">التغطية</a>
    {% endpage_header %}

    {% kpi_strip %}
      {% kpi "الأجنحة" 5 sub="طابقان" %}
      {% kpi "الغياب" 12 tone="red" href=url %}
    {% endkpi_strip %}

    {% section_card "الغائبون اليوم" meta=absent|length icon="user-x" empty="لم يغب أحد" %}
      {% for s in absent %}…{% endfor %}
    {% endsection_card %}

    {% entity_card "جناح 1" who=supervisor.full_name count="164 طالباً" %}
      {% entity_chips %}{% for c in sections %}<span class="chip">{{ c }}</span>{% endfor %}{% endentity_chips %}
      {% entity_status tone="warning" %}الحصّة 7 · حتّى 13:30{% endentity_status %}
    {% endentity_card %}

    {% empty_state "لا توجد نتائج" sub="جرّب بحثاً آخر" icon="inbox" %}

والقواعدُ السبع التي تحرسها (صفحة «دستور بطاقات SchoolOS»):
1. بطاقةُ الرقم سطرٌ واحد، وستٌّ على الأكثر في الشريط.
2. الرقمُ يُقال مرّة — والتفصيلُ لا يكرّر الاسم.
3. ترويسةُ القسم شريطٌ عنّابيٌّ واحد.
4. بطاقةُ الكيان ثلاثةُ أسطر: من وكم، ثمّ الرقاقات، ثمّ الحالة.
5. لا نثرَ بين البطاقات — الشرحُ تلميح.
6. العرضُ على قدر المحتوى.
7. حالةٌ فارغةٌ واحدة، ولونٌ من رموز المنصّة وحدها.

والخطأُ في الاستعمال (سابعُ بطاقة، لونٌ لا رمزَ له، بطاقةُ كيانٍ بسطرٍ رابع)
`TemplateSyntaxError` لا رسمٌ صامت: يظهر في أوّل اختبارٍ يعرض الصفحة.
"""

from __future__ import annotations

import re

from django import template
from django.template.loader import render_to_string
from django.utils.html import format_html
from django.utils.safestring import mark_safe

register = template.Library()

#: أقصى بطاقات الشريط — ما زاد يُقسَّم أو يُطوى تحت «المزيد».
MAX_KPIS = 6

#: ألوانُ بطاقة الرقم — كلٌّ منها صنفٌ في custom.css يعرّف `--kc` و`--kc-fg` من الرموز.
KPI_TONES = ("maroon", "green", "blue", "red", "amber", "teal", "orange", "purple", "sky")

#: حالاتُ السطر الثالث في بطاقة الكيان — دلالةٌ لا زينة.
STATUS_TONES = ("neutral", "success", "warning", "danger", "info")

#: علامةٌ يضعها كلُّ `kpi` فيعدّها الشريط — ولا تظهر في الصفحة.
_KPI_MARK = "data-ui-kpi"
_CHIPS_MARK = "data-ui-entity-chips"
_STATUS_MARK = "data-ui-entity-status"


def _require(value, tag: str, what: str):
    if value in (None, ""):
        raise template.TemplateSyntaxError(f"{tag}: {what} مطلوب")
    return value


def _tone(value: str, allowed: tuple[str, ...], tag: str) -> str:
    if value not in allowed:
        raise template.TemplateSyntaxError(
            f"{tag}: لونٌ {value!r} لا رمزَ له — المتاح: {', '.join(allowed)}"
        )
    return value


# ── 1. شريطُ الأرقام ──────────────────────────────────────────────────────


@register.simple_tag
def kpi(label, value, sub="", tone="maroon", href="", title=""):
    """بطاقةُ رقمٍ في سطرٍ واحد: الاسمُ ثمّ الرقمُ ثمّ تفصيلٌ قصير.

    `value` صفرٌ يُعرض صفراً — فغيابُ الغياب رقمٌ لا فراغ.
    """
    _require(label, "kpi", "الاسم")
    if value is None or value == "":
        raise template.TemplateSyntaxError(f"kpi «{label}»: الرقم مطلوب")
    return mark_safe(
        render_to_string(
            "components/ui/kpi.html",
            {
                "label": label,
                "value": value,
                "sub": sub,
                "tone": _tone(tone, KPI_TONES, "kpi"),
                "href": href,
                "title": title,
                "mark": _KPI_MARK,
            },
        )
    )


@register.simple_block_tag
def kpi_strip(content, label="أرقام الصفحة"):
    """شريطُ بطاقات الرقم — وما زاد على ستٍّ خطأٌ لا التفاف."""
    count = content.count(_KPI_MARK)
    if count == 0:
        raise template.TemplateSyntaxError("kpi_strip: شريطٌ بلا بطاقة — احذفه")
    if count > MAX_KPIS:
        raise template.TemplateSyntaxError(
            f"kpi_strip: {count} بطاقات — الحدُّ {MAX_KPIS}؛ اطوِ الباقي تحت «المزيد»"
        )
    return format_html(
        '<div class="ui-kpis" role="list" aria-label="{}">{}</div>',
        label,
        content,
    )


# ── 2. بطاقةُ القسم ───────────────────────────────────────────────────────


@register.simple_block_tag
def section_card(
    content, title, meta="", icon="", empty="لا توجد بيانات", empty_sub="", flush=False
):
    """قسمٌ بترويسةٍ عنّابيّة — والعددُ أو الفترةُ في طرفها لا في سطرٍ تحتها.

    والمحتوى الفارغ (حلقةٌ بلا عناصر) يُرسم حالةً فارغةً موحّدة، فلا تحتاج الصفحةُ
    `{% empty %}` تكتب فيه جملتَها الخاصّة. و`flush` يُلغي الحشوَ لجدولٍ يملأ البطاقة.
    """
    _require(title, "section_card", "العنوان")
    body = content if content.strip() else None
    return mark_safe(
        render_to_string(
            "components/ui/section_card.html",
            {
                "title": title,
                "meta": meta,
                "icon": icon,
                "body": body,
                "empty": empty,
                "empty_sub": empty_sub,
                "flush": flush,
            },
        )
    )


# ── 3. بطاقةُ الكيان ──────────────────────────────────────────────────────


@register.simple_block_tag
def entity_chips(content):
    return format_html('<div class="ui-entity__chips" {}>{}</div>', _CHIPS_MARK, content)


@register.simple_block_tag
def entity_status(content, tone="neutral", title=""):
    return format_html(
        '<div class="ui-entity__status is-{}" {}{}>{}</div>',
        _tone(tone, STATUS_TONES, "entity_status"),
        _STATUS_MARK,
        format_html(' title="{}"', title) if title else "",
        content,
    )


@register.simple_block_tag
def entity_card(content, title, who="", count="", href="", tone="maroon", badge="", badge_title=""):
    """كيانٌ في ثلاثة أسطر: من وكم · الرقاقات · الحالة.

    الاسمُ الطويلُ يُقصّ بنقاطٍ وكاملُه في التلميح. وما يُكتب في المحتوى غيرُ
    `entity_chips` و`entity_status` مرّةً لكلٍّ منهما خطأ — فالسطرُ الرابع هو
    الفقرةُ التي كانت تُطيل البطاقة.
    """
    _require(title, "entity_card", "العنوان")
    chips, status = content.count(_CHIPS_MARK), content.count(_STATUS_MARK)
    if chips > 1 or status > 1:
        raise template.TemplateSyntaxError(
            f"entity_card «{title}»: سطرُ رقاقاتٍ واحدٌ وسطرُ حالةٍ واحد — لا أكثر"
        )
    if _strip_known_lines(content).strip():
        raise template.TemplateSyntaxError(
            f"entity_card «{title}»: محتوى خارج entity_chips/entity_status — "
            "الشرحُ تلميحٌ لا سطرٌ رابع"
        )
    return mark_safe(
        render_to_string(
            "components/ui/entity_card.html",
            {
                "title": title,
                "who": who,
                "count": count,
                "href": href,
                "tone": _tone(tone, KPI_TONES, "entity_card"),
                "badge": badge,
                "badge_title": badge_title,
                "content": content,
            },
        )
    )


_KNOWN_LINE_RE = re.compile(
    r'<div class="ui-entity__(?:chips|status)[^"]*"[^>]*data-ui-entity-(?:chips|status)[^>]*>.*?</div>',
    re.S,
)


def _strip_known_lines(content: str) -> str:
    """ما يبقى من المحتوى بعد طرح سطرَي الرقاقات والحالة — ويجب أن يكون فراغاً."""
    return _KNOWN_LINE_RE.sub("", content)


# ── 4. الحالةُ الفارغة ────────────────────────────────────────────────────


@register.simple_tag
def empty_state(title="لا توجد بيانات", sub="", icon="inbox", compact=True):
    return mark_safe(
        render_to_string(
            "components/empty_state.html",
            {"title": title, "subtitle": sub, "icon": icon, "compact": compact},
        )
    )


# ── 5. ترويسةُ الصفحة ─────────────────────────────────────────────────────


@register.simple_block_tag
def page_header(content, title, subtitle="", icon=""):
    """عنوانُ الصفحة وسطرُها الوصفيّ وإجراءاتُها — إطارٌ واحدٌ بدل ثلاثة."""
    _require(title, "page_header", "العنوان")
    return mark_safe(
        render_to_string(
            "components/ui/page_header.html",
            {"title": title, "subtitle": subtitle, "icon": icon, "actions": content},
        )
    )

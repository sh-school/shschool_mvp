"""ترويسةُ عمودٍ تُفرَز من الخادم — نفسُ مظهرِ الفرز في المتصفّح.

    {% load sorting %}
    {% sort_th sort "date" "التاريخ" %}

تُخرج `<th>` كاملةً بـ `aria-sort` ورابطٍ يحمل `?sort=&dir=` مع بقيّة معاملات
الرابط كما هي — فالبحثُ والسنةُ والصفحةُ لا تضيع بنقرةِ فرز.

و`target` — حين يُمرَّر — يجعل النقرةَ تُبدّل الجدولَ وحدَه بـ HTMX بدل أن
تُعيد تحميلَ الصفحة كلِّها: الرابطُ يبقى كما هو لمن لا جافاسكربت عنده، وتُضاف
إليه `hx-get` تستبدل العنصرَ المستهدَف. وبغير ذلك يظلّ الفرزُ ملاحةً كاملة.
"""

from __future__ import annotations

from django import template
from django.utils.html import format_html

register = template.Library()


@register.simple_tag(takes_context=True)
def sort_th(context, state, key, label, css="", target=""):
    """ترويسةٌ قابلةٌ للفرز: تعكس الاتّجاهَ عند إعادة النقر، وتبدأ تصاعديّاً."""
    request = context.get("request")
    params = request.GET.copy() if request else {}
    active = bool(state) and state.key == key
    # النقرُ على العمود النشط يعكس اتّجاهَه، وعلى غيره يبدأ باتّجاهه الطبيعيّ.
    if active:
        nxt = "asc" if state.descending else "desc"
    else:
        nxt = "desc" if (state and state.starts_desc(key)) else "asc"

    if hasattr(params, "setlist"):
        params.setlist("sort", [key])
        params.setlist("dir", [nxt])
        params.pop("page", None)  # الفرزُ يُعيد الترتيبَ كلَّه فيعود القارئُ للصفحة الأولى
        query = params.urlencode()
    else:  # pragma: no cover - قالبٌ بلا request
        query = f"sort={key}&dir={nxt}"

    aria = "none"
    arrow = ""
    if active:
        aria = "descending" if state.descending else "ascending"

    # التبديلُ الجزئيّ: الجدولُ وحدَه يُستبدَل، فلا يقفز القارئُ إلى رأس الصفحة
    # ولا تضيع الترويسةُ التي نقر عليها من أمام عينيه.
    htmx = ""
    if target:
        htmx = format_html(
            ' hx-get="?{}" hx-target="{}" hx-swap="outerHTML" hx-push-url="true"',
            query,
            target,
        )

    return format_html(
        '<th scope="col" class="is-sortable {}" aria-sort="{}">'
        '<a class="th-sort" href="?{}" aria-label="رتّب حسب {}"{}>'
        '<span class="th-sort-label">{}</span>'
        '<span class="th-sort-arrow" aria-hidden="true">{}</span></a></th>',
        css,
        aria,
        query,
        label,
        htmx,
        label,
        arrow,
    )

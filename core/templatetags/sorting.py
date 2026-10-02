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


def _sort_link(context, state, key, label, target):
    """رابطُ فرزٍ واحد: (الرابطُ HTML، هل العمودُ نشطٌ، الاتّجاهُ إن نشط)."""
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

    # التبديلُ الجزئيّ: الجدولُ وحدَه يُستبدَل، فلا يقفز القارئُ إلى رأس الصفحة
    # ولا تضيع الترويسةُ التي نقر عليها من أمام عينيه.
    htmx = ""
    if target:
        htmx = format_html(
            ' hx-get="?{}" hx-target="{}" hx-swap="outerHTML" hx-push-url="true"',
            query,
            target,
        )

    link = format_html(
        '<a class="th-sort" href="?{}" aria-label="رتّب حسب {}"{}>'
        '<span class="th-sort-label">{}</span>'
        '<span class="th-sort-arrow" aria-hidden="true"></span></a>',
        query,
        label,
        htmx,
        label,
    )
    return link, active


def _aria(state, active):
    if not active:
        return "none"
    return "descending" if state.descending else "ascending"


@register.simple_tag(takes_context=True)
def sort_th(context, state, key, label, css="", target=""):
    """ترويسةٌ قابلةٌ للفرز: تعكس الاتّجاهَ عند إعادة النقر، وتبدأ تصاعديّاً."""
    link, active = _sort_link(context, state, key, label, target)
    return format_html(
        '<th scope="col" class="is-sortable {}" aria-sort="{}">{}</th>',
        css,
        _aria(state, active),
        link,
    )


@register.simple_tag(takes_context=True)
def sort_th_stack(context, state, key1, label1, key2, label2, css="", target=""):
    """ترويسةٌ لعمودٍ يحمل قيمتَين فوق بعض (سطران في الخليّة): كلُّ سطرٍ رابطُ فرزٍ بمفتاحه.

    السطرُ الأوّل `(key1، label1)` والثاني `(key2، label2)`؛ ومفتاحٌ فارغٌ يجعل العنوانَ نصّاً بلا فرز
    (الجوّالُ مخزَّنٌ مشفَّراً فلا يُفرَز). والعمودُ نشطٌ (`aria-sort`) إن نُشط أحدُ مفتاحَيه.
    """
    parts = []
    active_any = False
    for key, label in ((key1, label1), (key2, label2)):
        if key:
            link, active = _sort_link(context, state, key, label, target)
            active_any = active_any or active
            parts.append(link)
        else:
            parts.append(format_html('<span class="th-sort th-plain">{}</span>', label))
    return format_html(
        '<th scope="col" class="is-sortable is-stacked {}" aria-sort="{}">{}{}</th>',
        css,
        _aria(state, active_any),
        parts[0],
        parts[1],
    )


@register.simple_tag(takes_context=True)
def page_query(context, number):
    """سلسلةُ الاستعلام لصفحةٍ أخرى — بكلّ ما قبلها من ترشيحٍ وبحثٍ وفرز.

    كان رابطُ الصفحة `?page=2` وحدَه، فيُسقط `grade` و`q` و`status` و`sort`
    معاً: يختار القارئُ الصفَّ السابعَ ثمّ ينقر «2» فتُفتح له الصفحةُ الثانية
    من **كلّ** المدرسة — والقائمةُ المنسدلةُ ما زالت تقول «G7»، فيظنّ ما يراه
    سابعاً وهو غيرُه. وهذا أسوأُ من ضياع الترشيح: شاشةٌ تكذب ولا تقول.

    فتُنسخ معاملاتُ الرابط كما هي ويُبدَّل `page` وحدَه.
    """
    request = context.get("request")
    if request is None:  # pragma: no cover - قالبٌ بلا request
        return f"page={number}"
    params = request.GET.copy()
    params.setlist("page", [str(number)])
    return params.urlencode()

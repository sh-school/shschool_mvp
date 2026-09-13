"""
tests/test_mobile_layout.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━
المنصّةُ تُفتح على الهاتف كما تُفتح على الحاسوب — ما قِيس لا يعود.

مُسحت يومَ 2026-09-13 ثمانٍ وستّون صفحةً بعروض 360 و390 و414 داخل إطاراتٍ
بعرضٍ دقيق، فوُجد:

  - صفحاتٌ تُسحب جانباً: الجدولُ العامّ 353px، والزيارات 394px، والجدولةُ
    الذكيّة 54px.
  - جدولٌ مقصوصٌ لا يُمرَّر: جدولا الأجراس في `/wings/` 254px.
  - حقولٌ بخطّ 12px في 27 صفحة — Safari يُكبّر الصفحةَ عند الكتابة.
  - زرُّ الرجوع 22×22px في كلّ صفحة، دون أدنى WCAG (24px).
  - والجدولُ العامّ على الهاتف: ستٌّ وثلاثون خانةً بعرض ثمانية بكسلات.

هذه حرّاسٌ ساكنة على **القواعد التي أصلحتها**، لا على التخطيط نفسِه — التخطيطُ
لا يُقاس إلّا في متصفّح. فهي تمنع رجوعَ الأسباب المعروفة، ولا تكشف جديدَها.
"""

import pathlib
import re

from tests.css_contrast import iter_rules

CSS_PATH = pathlib.Path("static/css/custom.css")
SHEET = pathlib.Path("templates/schedule/print_schedule.html")
TEMPLATES = pathlib.Path("templates")


def _rules():
    return list(iter_rules(CSS_PATH.read_text(encoding="utf-8")))


def _decl(selector, prop, *, media=None):
    """قيمةُ خاصّيّةٍ لمُحدِّدٍ بعينه — خارج كلّ `@media` ما لم يُطلب غيرُه."""
    found = None
    for sel, decls, ctx in _rules():
        parts = {" ".join(p.split()) for p in sel.split(",")}
        if selector not in parts or prop not in decls:
            continue
        medias = [c for c in ctx if c.startswith("@media")]
        if media is None and medias:
            continue
        if media is not None and not any(media in m for m in medias):
            continue
        found = decls[prop]
    return found


def _px(value):
    m = re.search(r"(\d+(?:\.\d+)?)px", value or "")
    return float(m.group(1)) if m else None


# ══════════════════════════════════════════════════════════════════
# ١. لا جدولَ مقصوصاً بلا تمرير
# ══════════════════════════════════════════════════════════════════


def test_the_table_wrapper_scrolls_instead_of_cutting():
    """`.table-wrap` كان `overflow: hidden` لقصّ الزوايا — فقصّ الجداولَ معها."""
    ox = _decl(".table-wrap", "overflow-x")
    overflow = _decl(".table-wrap", "overflow")
    assert ox in {"auto", "scroll"}, (
        f"`.table-wrap` بـ`overflow-x: {ox}` و`overflow: {overflow}` — "
        "الجدولُ الأعرضُ من غلافه يُقصّ ولا تُرى أعمدتُه في الهاتف"
    )


def test_the_observations_table_sits_in_a_scroll_wrapper():
    """ثمانيةُ أعمدةٍ بلا غلافٍ كانت تدفع الصفحةَ 394px."""
    html = (TEMPLATES / "quality" / "observation_list.html").read_text(encoding="utf-8")
    table = html.index('<table class="table table-qatar"')
    before = html[:table]
    assert before.rfind('<div class="table-wrap">') > before.rfind(
        "</div>"
    ), "جدولُ الزيارات خارج `.table-wrap`"


# ══════════════════════════════════════════════════════════════════
# ٢. لا شريطَ يدفع الصفحة
# ══════════════════════════════════════════════════════════════════


def test_page_actions_wrap():
    """`flex-wrap` وحدَه لا يكفي: `flex-shrink: 0` يُبقي الصفَّ بعرض أزراره.

    فالجدولةُ الذكيّة بقيت 54px خارج الشاشة بعد إضافة `wrap` — حتى سُقِّف العرض.
    """
    assert _decl(".page-actions", "flex-wrap") == "wrap", "أزرارُ الصفحة لا تنكسر سطراً"
    assert (
        _decl(".page-actions", "max-width") == "100%"
    ), "صفُّ الأزرار بلا سقف — لا يبلغ حدّاً ينكسر عنده"


def test_the_schedule_toolbar_wraps_on_phones_and_holds_one_line_on_desktop():
    """الهاتفُ أوّلاً: ينكسر افتراضاً، ولا يُمنع الانكسارُ إلّا في الحاسوب.

    وقرارُ 2026-09-06 (سطرٌ واحدٌ على الحاسوب) باقٍ في `min-width`.
    """
    assert (
        _decl(".schedule-tools", "flex-wrap") == "wrap"
    ), "شريطُ أدوات الجدول لا ينكسر في الهاتف — كان يدفع الصفحةَ 353px"
    assert (
        _decl(".schedule-tools", "flex-wrap", media="min-width") == "nowrap"
    ), "قرارُ «سطرٌ واحدٌ على الحاسوب» سقط"
    assert (
        _decl(".schedule-tools > .form-select", "min-width") or ""
    ).strip() == "0", "القائمةُ في الهاتف بحدٍّ أدنى — تتجاوز الشاشةَ بطول أطول خيار"


def test_no_schedule_toolbar_form_forces_inline_by_hand():
    """`style="display:inline"` كان يغلب قاعدةَ الهاتف فيتكدّس الحقلان."""
    for name in ("print_view.html", "pages_view.html"):
        html = (TEMPLATES / "schedule" / name).read_text(encoding="utf-8")
        assert '<form method="get" style="display:inline">' not in html, name


# ══════════════════════════════════════════════════════════════════
# ٣. الحقلُ لا يُكبّر الصفحة
# ══════════════════════════════════════════════════════════════════


def test_phone_inputs_are_at_least_16px():
    """دون 16px يُكبّر Safari الصفحةَ عند التركيز ولا يُرجعها.

    والقاعدةُ في `utilities` لأنّ قواعدَ `modules` تُعلن خطَّ حقولها أصغر،
    و`modules` تغلب `components` أيّاً كان الوزن.
    """
    hits = []
    for sel, decls, ctx in _rules():
        if "font-size" not in decls:
            continue
        if not any("max-width" in c and "640px" in c for c in ctx):
            continue
        if not any(re.match(r"@layer\s+utilities", c) for c in ctx):
            continue
        parts = {" ".join(p.split()) for p in sel.split(",")}
        if {"select", "textarea"} <= parts:
            hits.append(decls["font-size"])
    assert hits, "لا قاعدةَ هاتفٍ في `utilities` تضبط خطَّ الحقول"
    assert any("16px" in h for h in hits), f"خطُّ الحقول في الهاتف: {hits}"


# ══════════════════════════════════════════════════════════════════
# ٤. أهدافُ اللمس
# ══════════════════════════════════════════════════════════════════


def test_the_back_button_meets_the_minimum_target():
    """WCAG 2.5.8 (AA): ‏24px — وكان 22px في كلّ صفحة."""
    w, h = _px(_decl(".bc-back", "width")), _px(_decl(".bc-back", "height"))
    assert w and h and w >= 24 and h >= 24, f"`.bc-back` {w}×{h}px"


# ══════════════════════════════════════════════════════════════════
# ٥. الجدولُ العامّ على الهاتف — يُمرَّر ولا يُحشر (الخيارُ أ)
# ══════════════════════════════════════════════════════════════════


def _narrow_embed_block():
    html = SHEET.read_text(encoding="utf-8")
    start = html.index("{% if embed and view_type == 'all_teachers' %}")
    end = html.index("{% endif %}", start)
    block = html[start:end]
    m = re.search(r"@media \(max-width: 900px\) \{(.*)", block, re.S)
    assert m, "لا كتلةَ للإطار الضيّق في طبقة التفاعل"
    return m.group(1)


def test_the_sheet_takes_its_natural_width_on_a_phone():
    block = _narrow_embed_block()
    assert (
        "table-layout: auto" in block and "width: max-content" in block
    ), "الجدولُ العامّ مضغوطٌ في عرض الإطار — خانةٌ بثمانية بكسلات"


def test_the_department_and_teacher_columns_stay_put_while_scrolling():
    """بلا تثبيتٍ يضيع السطرُ عن صاحبه بعد أوّل تمرير."""
    block = _narrow_embed_block()
    for cls in (".m-dept", ".m-name"):
        rule = re.search(re.escape(".schedule-matrix " + cls) + r"\s*\{([^}]*)\}", block)
        assert rule and "position: sticky" in rule.group(1), f"`{cls}` غيرُ مثبَّت"


def test_teacher_names_wrap_instead_of_being_cut():
    """«ومن قُصَّ اسمه بنقاطٍ ثلاثٍ لم يجد سطره» — تعليقُ الورقة نفسِها."""
    block = _narrow_embed_block()
    rule = re.search(r"\.schedule-matrix \.m-name\s*\{([^}]*)\}", block)
    assert rule and "white-space: normal" in rule.group(1), "الاسمُ يُقصّ في الهاتف"


def test_the_phone_rules_never_reach_paper():
    """الطباعةُ وملفُّ PDF لا يريان الكتلة: داخل `embed` و`@media screen`."""
    html = SHEET.read_text(encoding="utf-8")
    narrow = html.index("@media (max-width: 900px)")
    embed = html.rindex("{% if embed and view_type == 'all_teachers' %}", 0, narrow)
    screen = html.rindex("@media screen {", 0, narrow)
    assert embed < screen < narrow, "كتلةُ الهاتف خارج `embed` أو `@media screen`"

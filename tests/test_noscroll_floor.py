"""[DESIGN] «بلا تمرير» مشروطٌ بسعة النافذة (LAY-03، قرارُ المالك 2026-09-24).

صفحةُ `page-noscroll` تُمرِّر قوائمَها داخل بطاقاتها؛ فإن ضيّق ارتفاعُ النافذة منطقةً دون 15rem
نُزع الصنفُ فمُرِّرت الصفحةُ كلُّها. والقرارُ **قبل الرسم الأوّل** وإلّا قفزت الصفحة:
قيس CLS نحو 1.0 حين كان في base.js المؤجَّل، وعاد إلى مستواه (≤ 0.015) بعد نقله. فالحارسُ
يحفظ الترتيبَ الذي يجعله قبل الرسم، لا الشكلَ وحده.
"""

import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parents[1]
#: القالبُ بلا تعليقات جانغو (`{# #}` وكتلةُ `{% comment %}`) — لا تصل الصفحة، وتعليقُ الرأس يذكر `</main>` نصّاً.
BASE = re.sub(
    r"\{#.*?#\}|\{% comment %\}.*?\{% endcomment %\}",
    "",
    (ROOT / "templates/base/base.html").read_text(encoding="utf-8"),
    flags=re.S,
)
BASE_JS = (ROOT / "static/js/base.js").read_text(encoding="utf-8")


def test_the_decision_runs_inline_right_after_the_content():
    main_end = BASE.index("</main>")
    script = BASE.index("window.fitNoscroll = function", main_end)
    call = BASE.index("window.fitNoscroll();", script)
    # لا شيءَ بين المحتوى والقرار إلّا وسمُ السكربت.
    between = BASE[main_end + len("</main>") : script]
    assert between.strip().startswith('<script nonce="{{ request.csp_nonce }}">')
    assert call > script


def test_first_paint_waits_for_the_decision():
    """`blocking="render"` على علامةٍ بعد القرار — فلا يُرسم نصفُ صفحةٍ طويلةٍ ثمّ يقفز."""
    head = BASE[: BASE.index("</head>")]
    link = re.search(r'<link rel="expect" href="#([\w-]+)" blocking="render">', head)
    assert link, "رأسُ الصفحة بلا انتظارٍ لقرار «بلا تمرير»"
    marker = BASE.index(f'id="{link.group(1)}"')
    assert marker > BASE.index("window.fitNoscroll();")


def test_the_floor_is_fifteen_rem_and_counts_only_squeezed_regions():
    body = BASE[BASE.index("window.fitNoscroll = function") : BASE.index("window.fitNoscroll();")]
    assert "15 * parseFloat(getComputedStyle(document.documentElement).fontSize)" in body
    # المنطقةُ القصيرةُ بتصميمها لا تُحسب: يجب أن تطول حين يُنزع الصنف.
    assert "el.clientHeight > h[i] + 1 && h[i] < floor" in body


def test_base_js_redecides_on_resize_and_swaps_but_not_on_load():
    """إعادةُ القرار عند `load` كانت تُحدث قفزةً (CLS 0.94 في قائمة الطلاب) بعد الرسم."""
    block = BASE_JS[BASE_JS.index("«بلا تمرير» مشروطٌ بسعة النافذة") :]
    assert "addEventListener('resize', later)" in block
    assert "addEventListener('htmx:afterSwap', later)" in block
    assert "addEventListener('load'" not in block


def _tighten_body() -> str:
    start = BASE_JS.index("function tighten()")
    return BASE_JS[start : BASE_JS.index("function settle()", start)]


def test_the_decision_is_tightened_once_when_the_fonts_are_ready():
    """القرارُ المضمَّن يجري والخطوطُ 0 من 8 فيقيس بخطّ الاحتياط؛ فيُشدَّد مرّةً بعد أن تجهز.

    قياسُ 2026-09-25: 78 من 945 خليّةً (8.3%) بقيت «بلا تمرير» ومنطقتُها دون 15rem بعد وصول Tajawal.
    """
    assert "document.fonts.ready.then(settle)" in BASE_JS
    assert "finally { if (window.noscrollReveal) window.noscrollReveal(); }" in BASE_JS
    assert "addEventListener('load'" not in BASE_JS[BASE_JS.index("function tighten()") :][:2000]


def test_the_tightening_is_a_read_only_filter_before_the_real_decision():
    """تبديلُ `page-noscroll` بعد الرسم ثمّ قياسُ التخطيط يُحدث CLS زائفاً (0.96 مقيسٌ ولو لم يتغيّر القرار).

    فالتشديدُ يقرأ فقط، ولا يستدعي القرارَ الحقيقيَّ (`fitNoscroll`) إلّا حين يُرجَّح الانقلاب — منطقةٌ تفيض ودون 15rem
    وليست قصيرةً بسقفٍ مكتوب — فلا تبديلَ بلا موجب. وتُستثنى مضاعِفاتُ الإدخال (ارتفاعُها من rows/size لا من النافذة).
    """
    body = _tighten_body()
    assert "classList.add" not in body, "المرشِّحُ لا يبدّل الصنف؛ القرارُ للدالّة الأمّ"
    assert "TEXTAREA|SELECT|INPUT" in body
    assert "15 * parseFloat(getComputedStyle(document.documentElement).fontSize)" in body
    assert "el.scrollHeight <= el.clientHeight + 1 || el.clientHeight >= floor" in body
    assert "cs.maxHeight" in body
    # الاستدعاءُ الوحيدُ للقرار بعد شرط الترجيح، ثمّ إعلانُ التغيّر لمن يحمل حالةً مرتبطةً بالصنف.
    assert body.index("if (!squeezed && ") < body.index("window.fitNoscroll()")
    assert "dispatchEvent(new Event('noscroll:changed'))" in body


def test_content_is_held_back_until_the_fonts_are_ready_but_never_beyond_half_a_second():
    """بلا الحجب تقع القفزةُ بعد الرسم (CLS 0.3–0.9 على ذاكرةٍ باردة)؛ ومعه ≤ 0.076 في 280 خليّة."""
    block = BASE[BASE.index("window.fitNoscroll();") :]
    block = block[: block.index('<template id="noscroll-fitted">')]
    assert (
        "m.style.opacity = '0'" in block
    ), "الحجبُ بـopacity لا visibility: visibility يُسقط التركيزَ وشجرةَ الوصول"
    assert "visibility" not in block.replace("بخلاف visibility", "").replace("لا visibility", "")
    assert (
        "m.classList.contains('page-noscroll')" in block
        and "document.fonts.status === 'loaded'" in block
    )
    assert "window.noscrollReveal = function () { m.style.opacity = ''" in block
    assert re.search(
        r"setTimeout\(function \(\) \{ if \(window\.noscrollReveal\) window\.noscrollReveal\(\); \}, 500\)",
        block,
    ), "لا كشفَ احتياطيّاً بعد 500ms: تعطّلُ base.js يُبقي المحتوى محجوباً"


def test_pages_that_tie_state_to_the_class_hear_the_change():
    """صندوقُ الإشعارات يَسِم منطقةَ التمرير (tabindex/role) ما دامت الصفحةُ بلا تمرير؛ فيُصلح وسومَه عند انقلابها."""
    inbox = (ROOT / "templates/notifications/inbox.html").read_text(encoding="utf-8")
    assert "document.addEventListener('noscroll:changed', sync)" in inbox


def test_a_primary_action_hidden_behind_an_inner_scroll_turns_the_page_scrollable():
    """D-24 (قرارُ المالك 2026-09-25): زرُّ الإجراء الرئيسيّ لا يُحجب خلف تمريرٍ داخليّ — بلا CSS جديد.

    قيس 97 من 945 خليّةً يقع فيها «إضافة الطالب» و«إرسال الاستدعاء» و«عيّن بديلاً» تحت طيّ بطاقةٍ تُمرَّر. فمعيارُ «الإجراءُ مرئيّ» شرطٌ ثانٍ للانقلاب
    إلى تمرير الصفحة، يُقاس والصنفُ `page-noscroll` قائمٌ (حين تكون البطاقةُ مقصوصةً فعلاً).
    """
    probe = BASE[
        BASE.index("window.primaryActionHidden = function") : BASE.index(
            "window.fitNoscroll = function"
        )
    ]
    assert "form button[type=submit].btn-primary" in probe
    # زرُّ صفٍّ في جدولٍ أو قائمةٍ تمريرُه بتصميمها، فلا يقلب الصفحة.
    assert "btn.closest('table, .plain-list')" in probe
    # الصفحةُ نفسُها (main) قد تكون حاوية التمرير القاصّة.
    assert "p !== document.body" in probe
    decision = BASE[
        BASE.index("window.fitNoscroll = function") : BASE.index("window.fitNoscroll();")
    ]
    assert "var actionHidden = window.primaryActionHidden(main);" in decision
    assert "actionHidden ||" in decision
    # يُقاس والصنفُ موضوع، لا بعد نزعه (وإلّا لم تكن البطاقةُ مقصوصةً).
    assert decision.index("primaryActionHidden(main)") < decision.index(
        "main.classList.remove('page-noscroll')"
    )


def test_the_fonts_pass_also_redecides_when_the_action_is_hidden():
    """القرارُ المضمَّن يقيس بخطّ الاحتياط؛ فيُعاد بعد جهوز الخطوط إن حُجب الزرُّ كما يُعاد لمنطقةٍ مضغوطة."""
    assert "window.primaryActionHidden(main)" in _tighten_body()

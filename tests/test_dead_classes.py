"""[DESIGN] كلُّ صنفٍ في custom.css يذكره شيءٌ يُرسم — وحالةُ حروفه كما تُكتب.

كان في الملفّ 65 صنفاً لا يذكرها قالبٌ ولا سكربتٌ ولا بايثون، في مئة قاعدةٍ
ونيّف (2026-09-14): بطاقاتُ `kpi-mini` و`kpi-ring` قبل مكوّنات الواجهة،
و`form-steps` لمعالجٍ لم يُبنَ، و`btn-light` و`badge-role`، ولكلٍّ نظيرٌ ليليّ.
فمن يبحث عن نمط بطاقة الرقم يجد ثلاثةً ولا يدري أيَّها الحيّ.

والصنفُ الذي يُركَّب وقتَ التشغيل — `kpi-{{ tone }}`، `'toast-' + type`،
`` `legend-dot--${t}` `` — لا يُكتب اسمُه كاملاً في أيّ مصدر، فتُعذَر كلُّ
أصناف البادئة. وهذا عذرٌ واسع: الحارسُ يُمسك الميّتَ الصريح لا كلَّ ميّت.

والشطرُ الثاني وُلد من علّةٍ لا من تنظيف: كانت قواعدُ بطاقة الإسناد
`.asg-APPROVED` بالحروف الكبيرة، والقالبُ يركّب الصنفَ من قيمة الخطّة
`approved` — والصنفُ حسّاسٌ لحالة الحرف، فما ظهر شريطُ الحالة لأحدٍ قطّ.
فالصنفُ ذو الحرف الكبير لا يُعذر ببادئةٍ: إمّا أن يُكتب حرفيّاً وإمّا أن يسقط.
"""

import re

from tests.css_contrast import iter_rules
from tests.test_design_tokens_resolve import CSS, _consumer_sources

#: أصنافٌ تضعها مكتبةٌ لا شيفرتُنا — HTMX يضيف `htmx-request` وأخواتِه أثناء الطلب.
LIBRARY_PREFIXES = ("htmx-",)

#: بادئةٌ يليها تركيبٌ: `{{`، `{%`، `${`، `' +`، `{name` (f-string).
DYNAMIC_RE = re.compile(r"([_a-zA-Z][\w-]*?[-_])(?:\{\{|\{%|\$\{|['\"]\s*\+|\{[a-z_])")


def _css_classes():
    classes = set()
    for selector, _, _ in iter_rules(CSS.read_text(encoding="utf-8")):
        if selector.startswith("@"):
            continue
        bare = re.sub(r"\[[^\]]*\]|url\([^)]*\)", "", selector)
        classes |= set(re.findall(r"\.(-?[_a-zA-Z][\w-]*)", bare))
    return classes


def _sources():
    words, prefixes = set(), set()
    for source in _consumer_sources():
        text = source.read_text(encoding="utf-8", errors="ignore")
        words |= set(re.findall(r"-?[_a-zA-Z][\w-]*", text))
        prefixes |= {p for p in DYNAMIC_RE.findall(text) if len(p) >= 3}
    return words, prefixes


def test_every_class_is_named_by_something_that_renders():
    words, prefixes = _sources()
    dead = sorted(
        name
        for name in _css_classes() - words
        if not name.startswith(LIBRARY_PREFIXES) and not any(name.startswith(p) for p in prefixes)
    )
    assert not dead, "أصنافٌ لا يذكرها قالبٌ ولا سكربتٌ ولا بايثون — احذف قواعدَها:\n  " + "\n  ".join(
        dead
    )


def test_no_class_waits_for_capitals_nothing_writes():
    words, _ = _sources()
    shouting = sorted(
        name for name in _css_classes() if re.search(r"[A-Z]", name) and name not in words
    )
    assert not shouting, (
        "أصنافٌ بحروفٍ كبيرةٍ لا تُكتب كذلك في أيّ مصدر — والصنفُ حسّاسٌ لحالة الحرف، "
        "فالقاعدةُ لا تقع:\n  " + "\n  ".join(shouting)
    )

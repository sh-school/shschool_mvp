"""[BUG] 2026-09-22: قائمةُ الجداول لا تفتح جداولَ الأقسام ولا المعلّم ولا الشعبة — تبقى على الجدول العامّ.

`static/js/page-nav.js` يشغّل كلَّ سكربتٍ مضمَّنٍ في الصفحة الواردة **داخل غلاف**
`(function(){ … })();` — كي لا تصطدم صفحتان تعلنان `const` واحداً في مستندٍ واحد.
فإعلانُ `function goToSchedule(…)` في سكربت القالب يصير محلّيّاً في الغلاف، و`actions.js`
يبحث عنه في `window[name]` فلا يجده ويخرج صامتاً: تتغيّر القائمةُ ولا يتغيّر الجدول.
والتحديثُ الكامل يُصلحه، لأنّ السكربتَ في التحميل الأوّل لا يُغلَّف — ولهذا بدا متقطّعاً.

فكلُّ دالّةٍ في قائمة `CALLABLE` البيضاء تُسنَد إلى `window` صراحةً في القالب
(`window.goToSchedule = function (…) {…};`)، ولا تُعلَن إعلاناً مجرّداً. والحارسُ ثابتٌ
لا يحتاج متصفّحاً: يقرأ القائمةَ من `actions.js` نفسِه، فاسمٌ يُضاف إليها غداً يُحرس معها.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ACTIONS_JS = ROOT / "static" / "js" / "actions.js"
TEMPLATES = ROOT / "templates"


def _callables() -> list[str]:
    source = ACTIONS_JS.read_text(encoding="utf-8")
    block = re.search(r"var CALLABLE = \[(.*?)\];", source, re.S)
    assert block, "لم تُوجد قائمةُ CALLABLE في actions.js — هل تغيّر اسمُها؟"
    return re.findall(r'"(\w+)"', block.group(1))


def test_the_callable_list_is_read():
    assert "goToSchedule" in _callables()


def test_no_template_declares_a_callable_as_a_bare_function():
    names = _callables()
    bare = re.compile(r"\bfunction\s+(" + "|".join(names) + r")\s*\(")
    offenders = [
        f"{path.relative_to(ROOT).as_posix()}: function {m.group(1)}(…)"
        for path in sorted(TEMPLATES.rglob("*.html"))
        for m in bare.finditer(path.read_text(encoding="utf-8"))
    ]
    assert not offenders, (
        "دالّةٌ يناديها data-call معلنةٌ إعلاناً مجرّداً — تضيع بعد التنقّل بتبديل المحتوى؛ "
        "أسندها إلى window صراحةً:\n  " + "\n  ".join(offenders)
    )

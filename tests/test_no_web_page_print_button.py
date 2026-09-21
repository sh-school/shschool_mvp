"""[DESIGN] لا زرَّ «طباعة صفحة الويب» — قرارُ المالك 2026-09-21.

الصفحةُ التفاعليّةُ لا تُطبع: ما يُطبع كشفٌ ورقيٌّ مصمَّمٌ للورق (`?print=1` أو قالبُ
`print_*`/`pdf/`)، وما يُصدَّر يمرّ بمسار التصدير (PDF/Excel). وقد كان زرُّ
`window.print()` في عشراتِ الصفحات يطبع الشاشةَ نفسَها — ترويسةً وقوائمَ وأزراراً — فيخرج
الورقُ بغير هويّةٍ ولا ترويسةِ مدرسةٍ ولا توقيع.

والحارسُ يمنع عودتَه:

* `js-print-btn` ممنوعٌ في أيّ مكان (كان مقبضُه في `base.js`).
* `data-action="print"` و`window.print(` مسموحان فقط في القوالب الورقيّة المسمّاة أدناه.

قالبٌ ورقيٌّ جديدٌ يضيف اسمَه إلى القائمة صراحةً، فيُسأل عنه في المراجعة.
"""

import pathlib
import re

ROOTS = [pathlib.Path("templates"), *sorted(pathlib.Path(".").glob("*/templates"))]
JS = pathlib.Path("static/js")

#: قوالبُ ورقيّةٌ (كشوفٌ وأوراقُ اعتماد) تبقى قابلةً للطباعة بقرار المالك: ليست صفحةَ ويب.
PAPER_TEMPLATES = {
    "components/credentials_sheet.html",  # ورقةُ اعتمادٍ تُسلَّم مرّة واحدة
    "schedule/print_schedule.html",  # الجدولُ الورقيّ
    "schedule/print_view.html",  # إطارُ الجدول الورقيّ
    "schedule/pages_view.html",  # إطارُ صفحات الجدول
    "wings/register_pdf.html",  # كشفُ الشعبة الورقيّ
}

#: ملفّاتُ JS المسموحُ لها باستدعاء `window.print()`: الإجراءُ العامّ للقوالب الورقيّة وفتحُ الطباعة التلقائيّ.
PAPER_SCRIPTS = {"actions.js", "print-on-open.js"}

_PRINT_ACTION = re.compile(r"""data-action\s*=\s*["']print["']""")
_WINDOW_PRINT = re.compile(r"\bwindow\.print\s*\(|\bcontentWindow\.print\s*\(")


def _read(path):
    return path.read_text(encoding="utf-8", errors="ignore")


def _templates():
    for root in ROOTS:
        for path in sorted(root.rglob("*.html")):
            yield path, path.relative_to(root).as_posix()


def test_the_web_page_print_hook_is_gone_everywhere():
    offenders = [str(path) for path, _ in _templates() if "js-print-btn" in _read(path)]
    offenders += [str(path) for path in sorted(JS.glob("*.js")) if "js-print-btn" in _read(path)]

    assert not offenders, f"مقبضُ طباعة الصفحة عاد: {offenders}"


def test_print_actions_live_only_in_paper_templates():
    offenders = []
    for path, name in _templates():
        text = _read(path)
        if (
            _PRINT_ACTION.search(text) or _WINDOW_PRINT.search(text)
        ) and name not in PAPER_TEMPLATES:
            offenders.append(name)

    assert not offenders, (
        "زرُّ طباعةٍ في صفحة ويب — الصفحةُ لا تُطبع (قرار 2026-09-21). "
        f"استعمل زرَّ التصدير (PDF/Excel)، أو أضف القالبَ الورقيَّ إلى PAPER_TEMPLATES: {offenders}"
    )


def test_window_print_in_scripts_is_limited_to_the_paper_helpers():
    offenders = [
        path.name
        for path in sorted(JS.glob("*.js"))
        if _WINDOW_PRINT.search(_read(path)) and path.name not in PAPER_SCRIPTS
    ]

    assert not offenders, f"window.print() خارج مساعدَي الورق: {offenders}"

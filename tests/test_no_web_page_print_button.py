"""[DESIGN] لا طباعةَ مباشرة — قرارُ المالك 2026-09-21، وتوكيدُه 2026-09-28 («طباعةٌ مباشرة تُلغى ويُكتفى بالتصدير»).

الصفحةُ التفاعليّةُ لا تُطبع، وما يُصدَّر يمرّ بمسار التصدير (PDF/Excel) لا بزرّ طباعةٍ مباشرة. وقد كان زرُّ
`window.print()` في عشراتِ الصفحات يطبع الشاشةَ نفسَها — ترويسةً وقوائمَ وأزراراً — فيخرج
الورقُ بغير هويّةٍ ولا ترويسةِ مدرسةٍ ولا توقيع.

والحارسُ يمنع عودتَه:

* `js-print-btn` ممنوعٌ في أيّ مكان (كان مقبضُه في `base.js`).
* `data-action="print"` وأيُّ استدعاءٍ لـ`.print(` (`window.print(`، `contentWindow.print(`، وأيُّ متغيّرٍ آخر
  ينتهي بـ`.print(`) مسموحان فقط في القوالب الورقيّة المسمّاة أدناه.
* `id`/`data-action` يحمل كلمة «print» في قيمته (مقبضُ زرّ طباعةٍ سابق) ممنوعٌ خارج القوالب الورقيّة ومكوّن
  الإطار المطبوع المركزيّ (`id="print-header"`/`id="print-footer"` في `templates/components/print/` — صندوقا
  الهامش لتصدير PDF، لا زرَّ طباعة).

قالبٌ ورقيٌّ جديدٌ يضيف اسمَه إلى القائمة صراحةً، فيُسأل عنه في المراجعة.
"""

import pathlib
import re

ROOTS = [pathlib.Path("templates"), *sorted(pathlib.Path(".").glob("*/templates"))]
JS = pathlib.Path("static/js")

#: قوالبُ ورقيّةٌ (كشوفٌ وأوراقُ اعتماد) تبقى قابلةً للطباعة بقرار المالك: ليست صفحةَ ويب.
#: (طلباتٌ متوازيةٌ تُفرغها واحداً واحداً 2026-09-28 — كشفُ كلمات المرور وكشفُ الشعبة لم يُدمجا بعدُ
#: حين كُتب هذا الطلب، فبقيا هنا حتى يندمجا.)
PAPER_TEMPLATES = {
    "components/credentials_sheet.html",  # ورقةُ اعتمادٍ تُسلَّم مرّة واحدة — طلبٌ منفصلٌ يحذف طباعتَها
    "wings/register_pdf.html",  # كشفُ الشعبة الورقيّ — طلبٌ منفصلٌ يحذف طباعتَه
}

#: ملفّاتُ JS المسموحُ لها باستدعاء `.print(`: الإجراءُ العامّ للقوالب الورقيّة الباقية، وفتحُ الطباعة
#: التلقائيّ لكشف الشعبة (يُحذف مع طلبه المنفصل).
PAPER_SCRIPTS = {"actions.js", "print-on-open.js"}

_PRINT_ACTION = re.compile(r"""data-action\s*=\s*["']print["']""")
_WINDOW_PRINT = re.compile(r"\.print\s*\(")
_PRINT_ID = re.compile(r"""\b(?:id|data-action)\s*=\s*["'][^"']*print[^"']*["']""", re.IGNORECASE)

#: مكوّنُ الإطار المطبوع المركزيّ يحمل `id="print-header"`/`id="print-footer"` — صندوقا هامش PDF
#: (`position: running()`)، لا زرَّ طباعة؛ مستثنيان من فحص `_PRINT_ID` وحدَه.
PRINT_ID_EXEMPT = {"components/print/frame_header.html", "components/print/frame_footer.html"}


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


def test_no_stray_print_id_or_data_action_anywhere():
    """`id`/`data-action` بقيمةٍ تحمل «print» — بقيّةُ زرٍّ محذوفٍ لم يُنظَّف تماماً."""
    offenders = []
    for path, name in _templates():
        if name in PAPER_TEMPLATES or name in PRINT_ID_EXEMPT:
            continue
        if _PRINT_ID.search(_read(path)):
            offenders.append(name)

    assert not offenders, f"بقيّةُ زرّ طباعةٍ (id/data-action) لم تُحذف بالكامل: {offenders}"


def test_window_print_in_scripts_is_limited_to_the_paper_helpers():
    offenders = [
        path.name
        for path in sorted(JS.glob("*.js"))
        if _WINDOW_PRINT.search(_read(path)) and path.name not in PAPER_SCRIPTS
    ]

    assert not offenders, f"window.print() خارج مساعدَي الورق: {offenders}"

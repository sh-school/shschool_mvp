"""تصييرُ md إلى HTML — العرضُ وحدَه؛ الحارسُ ضدّ الخروج عن الجذر في `services.safe_resolve`."""

from __future__ import annotations

import re

import markdown as markdown_lib

_EXTENSIONS = ["tables", "fenced_code", "toc", "sane_lists"]

#: جدولُ md يخرج `<table>…</table>` خاماً — يُغلَّف بمكوّن العرض القائم `.table-wrap`
#: (تمريرٌ أفقيٌّ وترويسةٌ ثابتة، `20-components.css`) بدل صنفٍ جديد.
_TABLE_OPEN = re.compile(r"<table>")
_TABLE_CLOSE = re.compile(r"</table>")


def render_markdown(text: str) -> str:
    """يصيّر نصَّ md إلى HTML — جداول وكتلُ شيفرةٍ وقائمةُ محتوى (`{{ toc }}` لا يُستعمل هنا)."""
    html = markdown_lib.markdown(text, extensions=_EXTENSIONS, output_format="html5")
    html = _TABLE_OPEN.sub('<div class="table-wrap"><table>', html)
    html = _TABLE_CLOSE.sub("</table></div>", html)
    return html

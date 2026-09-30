"""تصييرُ md إلى HTML — العرضُ وحدَه؛ الحارسُ ضدّ الخروج عن الجذر في `services.safe_resolve`."""

from __future__ import annotations

import re
from dataclasses import dataclass

import markdown as markdown_lib

_EXTENSIONS = ["tables", "fenced_code", "toc", "sane_lists"]

#: جدولُ md يخرج `<table>…</table>` خاماً — يُغلَّف بمكوّن العرض القائم `.table-wrap`
#: (تمريرٌ أفقيٌّ وترويسةٌ ثابتة، `20-components.css`) بدل صنفٍ جديد.
_TABLE_OPEN = re.compile(r"<table>")
_TABLE_CLOSE = re.compile(r"</table>")


@dataclass
class RenderedDoc:
    """محتوى ملفٍّ مصيَّرٌ: النصُّ وفهرسُ عناوينه (فارغٌ إن لم توجد عناوين)."""

    content_html: str
    toc_html: str
    has_toc: bool


def render_markdown(text: str) -> RenderedDoc:
    """يصيّر نصَّ md إلى HTML — جداول وكتلُ شيفرةٍ، وفهرسَ عناوينَ (`toc`) لعمودٍ جانبيّ."""
    md = markdown_lib.Markdown(extensions=_EXTENSIONS, output_format="html5")
    html = md.convert(text)
    html = _TABLE_OPEN.sub('<div class="table-wrap"><table>', html)
    html = _TABLE_CLOSE.sub("</table></div>", html)
    has_toc = bool(getattr(md, "toc_tokens", None))
    return RenderedDoc(content_html=html, toc_html=md.toc, has_toc=has_toc)

"""تصييرُ md إلى HTML — العرضُ وحدَه؛ الحارسُ ضدّ الخروج عن الجذر في `services.safe_resolve`."""

from __future__ import annotations

import markdown as markdown_lib

_EXTENSIONS = ["tables", "fenced_code", "toc", "sane_lists"]


def render_markdown(text: str) -> str:
    """يصيّر نصَّ md إلى HTML — جداول وكتلُ شيفرةٍ وقائمةُ محتوى (`{{ toc }}` لا يُستعمل هنا)."""
    return markdown_lib.markdown(text, extensions=_EXTENSIONS, output_format="html5")

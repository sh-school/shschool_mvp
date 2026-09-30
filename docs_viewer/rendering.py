"""تصييرُ md إلى HTML — العرضُ وحدَه؛ الحارسُ ضدّ الخروج عن الجذر في `services.safe_resolve`."""

from __future__ import annotations

import posixpath
import re
from dataclasses import dataclass

import markdown as markdown_lib
from django.urls import reverse

_EXTENSIONS = ["tables", "fenced_code", "sane_lists"]

#: جدولُ md يخرج `<table>…</table>` خاماً — يُغلَّف بمكوّن العرض القائم `.table-wrap`
#: (تمريرٌ أفقيٌّ وترويسةٌ ثابتة، `20-components.css`) بدل صنفٍ جديد.
_TABLE_OPEN = re.compile(r"<table>")
_TABLE_CLOSE = re.compile(r"</table>")

#: صورةُ md — `src="..."` داخل وسم `<img>` أيّاً كان ترتيبُ خصائصه الأخرى.
_IMG_SRC_RE = re.compile(r'(<img\b[^>]*\bsrc=")([^"]+)(")')


@dataclass
class RenderedDoc:
    """محتوى ملفٍّ مصيَّر."""

    content_html: str


def render_markdown(text: str, source_dir: str = "") -> RenderedDoc:
    """يصيّر نصَّ md إلى HTML — جداول وكتلُ شيفرة.

    `source_dir` مجلّدُ الملفّ المصدر نسبةً إلى جذر المشروع — يلزم لتصحيح مسارات
    الصور النسبيّة (`_rewrite_relative_images`؛ شعاراتٌ غالباً، مثل `README.md`
    الذي يشير إلى `assets/brand/…` نسبةً إلى موضعه هو لا إلى رابط العرض)."""
    md = markdown_lib.Markdown(extensions=_EXTENSIONS, output_format="html5")
    html = md.convert(text)
    html = _TABLE_OPEN.sub('<div class="table-wrap"><table>', html)
    html = _TABLE_CLOSE.sub("</table></div>", html)
    html = _rewrite_relative_images(html, source_dir)
    return RenderedDoc(content_html=html)


def _rewrite_relative_images(html: str, source_dir: str) -> str:
    """مسارُ صورةٍ نسبيٌّ في md نسبةٌ إلى موضع الملفّ نفسِه على القرص — لا إلى رابط
    `/docs/<مسار>/` الذي يُعرض منه، فتظهر مكسورةً (٤٠٤) بلا هذا التصحيح. المطلقُ
    والخارجيّ (`http(s)://`, `data:`, `/…`) يُترَك كما هو."""

    def repl(match: re.Match[str]) -> str:
        prefix, src, suffix = match.groups()
        if src.startswith(("http://", "https://", "data:", "/", "#")):
            return match.group(0)
        resolved = (
            posixpath.normpath(posixpath.join(source_dir, src))
            if source_dir
            else posixpath.normpath(src)
        )
        new_src = reverse("docs_viewer:asset", kwargs={"rel_path": resolved})
        return f"{prefix}{new_src}{suffix}"

    return _IMG_SRC_RE.sub(repl, html)

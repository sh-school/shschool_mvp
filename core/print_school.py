"""مصدرُ اسم المدرسة الواحدُ لترويسات PDF (W-20261107-023، قرارُ المالك 2026-11-07).

كان `core/pdf_utils.py` يستخرج الاسمَ بـregex من أوّل `<h1>` في `report-header` وإلا يضع «SchoolOS» — فتخرج قوالبُ كثيرةٌ بلا اسمٍ صحيح.
الآن يُمرَّر مصدرٌ واحدٌ إلى مسارات التوليد كلّها (WeasyPrint وPlaywright وxhtml2pdf): مدرسةُ الطلب الجاري (يضبطها
`ExportOrientMiddleware` ومشغّلُ مهامّ التصدير الخلفيّة)، فإن لم توجد فالاسمُ المقروء من وسوم القالب نفسه، فإن لم يوجد فنصٌّ عامٌّ — لا اسمَ المنصّة أبداً.
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any

#: البديلُ حين لا مدرسةَ في السياق ولا اسمَ في القالب — ليس اسمَ المنصّة.
FALLBACK_NAME = "المدرسة"
_PLATFORM_NAME = "schoolos"

#: مصدرُ المدرسة للطلب الجاري: كائنُ طلبٍ (يُقرأ كسولاً لأنّ المستخدم يُحلّ بعد الوسيط) أو كائنُ مدرسة.
_source: ContextVar[Any] = ContextVar("print_school_source", default=None)

_TAGS = re.compile(r"<[^>]+>")
#: مواضعُ الاسم في قوالب المنصّة: `report-header h1` ثمّ `school-name` ثمّ `pf-school` ثمّ `data-school-name`.
_HTML_PATTERNS = (
    re.compile(r'class="report-header".*?<h1[^>]*>(.*?)</h1>', re.DOTALL),
    re.compile(r'class="[^"]*\bschool-name\b[^"]*"[^>]*>(.*?)</', re.DOTALL),
    re.compile(r'class="[^"]*\bpf-school\b[^"]*"[^>]*>(.*?)</', re.DOTALL),
)


@contextmanager
def use_school(source: Any) -> Iterator[None]:
    """يجعل `source` (طلباً أو مدرسةً) مصدرَ الاسم طوال الكتلة ثم يعيد ما كان."""
    token = _source.set(source)
    try:
        yield
    finally:
        _source.reset(token)


def _name_of(obj: Any) -> str:
    return str(getattr(obj, "name", "") or "").strip()


def _from_source() -> str:
    src = _source.get()
    if src is None:
        return ""
    direct = _name_of(getattr(src, "school", None))
    if direct:
        return direct
    user = getattr(src, "user", None)
    getter = getattr(user, "get_school", None)
    if callable(getter):
        try:
            return _name_of(getter())
        except Exception:  # noqa: BLE001 — مستخدمٌ مجهولٌ أو قاعدةٌ غير جاهزة: ننتقل إلى القالب
            return ""
    return _name_of(src)


def _from_html(html_str: str) -> str:
    for pattern in _HTML_PATTERNS:
        m = pattern.search(html_str or "")
        if m:
            text = _TAGS.sub("", m.group(1)).strip()
            if text:
                return text
    return ""


def is_platform_name(text: str) -> bool:
    return text.strip().lower() == _PLATFORM_NAME


def resolve_school_name(html_str: str = "") -> str:
    """اسمُ المدرسة للترويسة: سياقُ الطلب ثمّ القالبُ ثمّ `FALLBACK_NAME`؛ «SchoolOS» لا يُقبل اسماً."""
    for candidate in (_from_source(), _from_html(html_str)):
        if candidate and not is_platform_name(candidate):
            return candidate
    return FALLBACK_NAME

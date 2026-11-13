"""
tests/test_export_button_guard.py
حارسُ زرّ التصدير — W-20261113-001

الخللُ: محتوى الوسم (سلسلةُ الاستعلام) يصل مهرَّباً من القالب (`&amp;`) أو حرفيّاً (`&`)،
فكان الوسمُ يهرّبه ثانيةً فيقرأ المتصفّحُ معاملاتٍ باسم `amp;teacher` فيُصدَّر غيرُ المعروض.

يغطّي:
  - شكلَ المحتوى الثلاثةَ: متغيّرٌ مهرَّب، و`&` حرفيّ، و`&amp;` حرفيّ.
  - `&` حرفيّ يتلوه اسمٌ يشبه كياناً (`&not=`) لا يُفكّ.
  - كلَّ قالبٍ يحمل وسم export_button: ناتجُ الوسم لأشكال المحتوى المستعملة فيه لا يُخرج «amp;».
"""

import html
import re
from pathlib import Path

import pytest
from django.utils.html import escape

from core.templatetags.ui import export_button

#: جذرُ المستودع: هذا الملفُّ في tests/.
_ROOT = Path(__file__).resolve().parents[1]

#: وسمُ export_button كما يُكتب في القالب: الوسطُ وسائطُه، والمحتوى ما بين الوسمين.
_BLOCK = re.compile(r"\{%\s*export_button\b([^%]*)%\}(.*?)\{%\s*endexport_button\s*%\}", re.DOTALL)
_KIND = re.compile(r'^\s*"(pdf|xlsx)"')
_HREF = re.compile(r'href="([^"]*)"')
#: متغيّرٌ يُعوَّض بقيمةٍ فيها `&` مهرَّبة كما يخرجها Django: يكفي لإظهار الخلل إن وُجد.
_SAMPLE_VAR = escape("a=1&b=2")


def _href(out: str) -> str:
    match = _HREF.search(out)
    assert match, out
    return match.group(1)


def test_variable_content_is_escaped_once():
    # {{ selection_query }} يصل مهرَّباً: `a=1&amp;b=2` — يُخرَج كما هو، لا `&amp;amp;`.
    out = export_button("a=1&amp;b=2", "pdf", href="/x/")
    assert _href(out) == "/x/a=1&amp;b=2"
    assert "amp;amp;" not in out


def test_literal_ampersand_is_escaped_once():
    # `&` حرفيّة في القالب (`?year={{ year }}&paper=A4`): تُهرَّب مرّةً فتصير `&amp;`.
    out = export_button("a=1&b=2", "xlsx", href="/x/")
    assert _href(out) == "/x/a=1&amp;b=2"


def test_literal_entity_in_template_is_not_doubled():
    # `&amp;` حرفيّةً في القالب (`&amp;q=…` في attendance_board): تُفكّ ثم تُهرَّب، فلا تتضاعف.
    out = export_button("a=1&amp;b=2", "pdf", href="/x/")
    assert _href(out) == "/x/a=1&amp;b=2"
    assert "amp;amp;" not in out


def test_name_that_looks_like_entity_is_kept():
    # `&not=` ليست كياناً (لا `;`): لا تُفكّ إلى «¬=» كما كان سيفعل html.unescape على النصّ كلّه.
    out = export_button("a=1&not=2&lt=3", "pdf", href="/x/")
    assert _href(out) == "/x/a=1&amp;not=2&amp;lt=3"


def _template_blocks():
    """(اسمُ القالب، النوع، المحتوى) لكلّ وسمِ export_button في templates/ بعد تعويض متغيّراته."""
    for path in sorted((_ROOT / "templates").rglob("*.html")):
        text = path.read_text(encoding="utf-8")
        for match in _BLOCK.finditer(text):
            kind = _KIND.match(match.group(1))
            if not kind:
                # نوعٌ يُمرَّر متغيّراً أو طباعةٌ بلا رابط: لا رابطَ هنا يُفحص.
                continue
            # وسومُ المنطق والتعليقات تُحذف، والمتغيّرات تُستبدل بقيمةٍ فيها `&`.
            content = re.sub(r"\{#.*?#\}|\{%.*?%\}", "", match.group(2), flags=re.DOTALL)
            content = re.sub(r"\{\{.*?\}\}", _SAMPLE_VAR, content, flags=re.DOTALL)
            yield path.name, kind.group(1), content


_BLOCKS = list(_template_blocks())


def test_template_scan_finds_export_buttons():
    # الحارسُ لا يمرّ فارغاً: القوالب فيها أزرارُ تصدير.
    assert len(_BLOCKS) > 20


@pytest.mark.parametrize(("name", "kind", "content"), _BLOCKS, ids=lambda v: str(v)[:40])
def test_no_export_link_in_templates_carries_double_escaped_amp(name, kind, content):
    out = export_button(content, kind, href="/x/")
    # المتصفّح يفكّ الكيانَ مرّةً في السمة: أيُّ `amp;` بعدها دليلُ تهريبٍ مزدوج.
    assert "amp;" not in html.unescape(_href(out)), (name, content)

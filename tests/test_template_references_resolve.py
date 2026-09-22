"""ما يشير إليه القالبُ موجود: أيقوناتُه معانٍ حقيقيّةٌ في القاموس، وآباؤه صفحاتٌ قائمة.

كانت `components/icon.html` تكتب `<use href="#icon-{{ name }}"/>` من ورقةٍ خارجيّة،
والمتصفّحُ لا يقول شيئاً حين لا يجد المعرَّف: لا خطأَ في الطرفيّة ولا في سجلّ
الخادم — خانةٌ فارغة وحسب. فاسمٌ مخترَعٌ كان يمرّ صامتاً حتّى يراه المستخدم.
الملفُّ والورقةُ محذوفان 2026-09-18 (`tests/test_icon_dictionary.py` يحرس
عدم عودتهما)؛ الباقي هنا معنى القاموس وحده.

وقد وقع أسوأُ منه: `components/empty_state.html` كان يطبع `icon` نصّاً خاماً،
فمن مرّر إليه اسمَ أيقونةٍ رأى الاسمَ بخطٍّ ضخمٍ مكانَ الرسم — «check-circle»
معروضةً بحروفها في شاشة غيابات المعلمين.
"""

import re
from pathlib import Path

import pytest

from core.icons import ICONS

TEMPLATES = Path(__file__).resolve().parent.parent / "templates"

EMPTY_STATE_ICON = re.compile(r'empty_state\.html["\']?\s+with[^%]*?\bicon=["\']([^"\']+)["\']')


def _templates():
    return sorted(TEMPLATES.rglob("*.html"))


def _calls(pattern):
    for path in _templates():
        text = path.read_text(encoding="utf-8")
        for name in pattern.findall(text):
            yield path.relative_to(TEMPLATES), name


@pytest.mark.parametrize("path,name", list(_calls(EMPTY_STATE_ICON)), ids=lambda v: str(v))
def test_the_empty_state_icon_is_a_real_meaning_not_a_glyph(path, name):
    """المكوّنُ يرسم أيقونةً الآن — فما يُمرَّر إليه معنًى في القاموس، لا رمزٌ ولا emoji."""
    assert (
        name in ICONS
    ), f"{path}: «{name}» ليس معنًى في core/icons.py — وكان يُطبَع بحروفه مكانَ الرسم"


def test_the_empty_state_renders_an_icon_element_not_bare_text():
    """الحارسُ الحقيقيّ: لو عاد المكوّنُ إلى الطباعة الخام لمرّ ما فوقه صامتاً."""
    body = (TEMPLATES / "components" / "empty_state.html").read_text(encoding="utf-8")

    assert "{% icon_named icon" in body
    assert "{{ icon }}" not in body, "طباعةُ الاسم خاماً هي العطبُ نفسُه"


# ── فتاتُ الخبز: كلُّ أبٍ يُشار إليه صفحةٌ قائمة ──────────────────────

#: `parent_url="/x/"` في `components/breadcrumbs.html` — والمسارُ حرفيٌّ لا
#: `{% url %}`، فلا يُخطئه أحدٌ عند الكتابة ولا يُنبّه أحدٌ عند التغيير.
BREADCRUMB_PARENT = re.compile(r'parent_url=["\']([^"\']+)["\']')


def _parents():
    seen = {}
    for path in _templates():
        for url in BREADCRUMB_PARENT.findall(path.read_text(encoding="utf-8")):
            if url.startswith("/"):
                seen.setdefault(url, []).append(str(path.relative_to(TEMPLATES)))
    return sorted(seen.items())


@pytest.mark.parametrize("url,users", _parents(), ids=lambda v: str(v))
def test_every_breadcrumb_parent_resolves(url, users):
    """أربعةٌ منها كانت تُرجع 404 — «الاحتياط» و«الجدول» و«الاستيراد».

    ونقرةُ فتات الخبز أوّلُ ما يفعله من ضلّ الطريق: أن تردّه إلى صفحةِ خطأ
    أسوأُ من ألّا يكون الرابطُ هناك أصلاً.
    """
    from django.urls import Resolver404, resolve

    try:
        resolve(url)
    except Resolver404:
        pytest.fail(f"«{url}» لا يُحلّ — ويُشار إليه من: {', '.join(sorted(set(users)))}")

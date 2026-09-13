"""ما يشير إليه القالبُ موجود: أيقوناتُه في ورقة الرموز، وآباؤه صفحاتٌ قائمة.

`components/icon.html` يكتب `<use href="#icon-{{ name }}"/>`، والمتصفّحُ لا يقول
شيئاً حين لا يجد المعرَّف: لا خطأَ في الطرفيّة ولا في سجلّ الخادم — خانةٌ فارغة
وحسب. فاسمٌ مخترَعٌ يمرّ صامتاً حتّى يراه المستخدم.

وقد وقع أسوأُ منه: `components/empty_state.html` كان يطبع `icon` نصّاً خاماً،
فمن مرّر إليه اسمَ أيقونةٍ رأى الاسمَ بخطٍّ ضخمٍ مكانَ الرسم — «check-circle»
معروضةً بحروفها في شاشة غيابات المعلمين.
"""

import re
from pathlib import Path

import pytest

TEMPLATES = Path(__file__).resolve().parent.parent / "templates"
SPRITE = TEMPLATES / "components" / "sprite.html"

#: `{% include "components/icon.html" with name="x" %}` — والاسمُ حرفيٌّ وحدَه؛
#: ما جاء من متغيّرٍ لا يُقرأ هنا ولا يُدَّعى أنّه فُحص.
ICON_CALL = re.compile(r'icon\.html["\']?\s+with\s+name=["\']([a-z0-9-]+)["\']')
EMPTY_STATE_ICON = re.compile(r'empty_state\.html["\']?\s+with[^%]*?\bicon=["\']([^"\']+)["\']')


def _sprite_names() -> set[str]:
    return set(re.findall(r'id="icon-([a-z0-9-]+)"', SPRITE.read_text(encoding="utf-8")))


def _templates():
    return sorted(TEMPLATES.rglob("*.html"))


def _calls(pattern):
    for path in _templates():
        text = path.read_text(encoding="utf-8")
        for name in pattern.findall(text):
            yield path.relative_to(TEMPLATES), name


def test_the_sprite_is_not_empty():
    """حارسٌ يقرأ ملفّاً فارغاً يمرّ دائماً — فيُتحقَّق من المصدر أوّلاً."""
    assert len(_sprite_names()) > 50


@pytest.mark.parametrize("path,name", list(_calls(ICON_CALL)), ids=lambda v: str(v))
def test_every_requested_icon_exists_in_the_sprite(path, name):
    assert name in _sprite_names(), f"{path}: لا أيقونةَ باسم «{name}» في ورقة الرموز"


@pytest.mark.parametrize("path,name", list(_calls(EMPTY_STATE_ICON)), ids=lambda v: str(v))
def test_the_empty_state_icon_is_a_sprite_name_not_a_glyph(path, name):
    """المكوّنُ يرسم أيقونةً الآن — فما يُمرَّر إليه اسمٌ لا رمزٌ ولا emoji."""
    assert name in _sprite_names(), f"{path}: «{name}» ليس اسمَ أيقونةٍ — وكان يُطبَع بحروفه مكانَ الرسم"


def test_the_empty_state_renders_an_icon_element_not_bare_text():
    """الحارسُ الحقيقيّ: لو عاد المكوّنُ إلى الطباعة الخام لمرّ ما فوقه صامتاً."""
    body = (TEMPLATES / "components" / "empty_state.html").read_text(encoding="utf-8")

    assert "components/icon.html" in body
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

"""[UX] شريط التصفّح يأتي من مكوّنه وحده — ولا يُكرّر جذره.

رأى المستخدم في الإنتاج على `/reports/`:

    الرئيسية / الرئيسية / التقارير والشهادات

لأن المكوّن يطبع «الرئيسية» بنفسه، وتسع عشرة صفحة كانت تُمرّرها إليه ثانيةً
بوصفها أباً:

    {% include "components/breadcrumbs.html" with
       parent_url="/dashboard/" parent_label="الرئيسية" current="..." %}

ولا شيء يكشفه: كلّ نصفٍ صحيحٌ وحده، والخطأ في اجتماعهما — كما كان في تصادم
أسماء النماذج.

وصفحةٌ واحدة كانت تكتب الشريط بيدها بدل المكوّن، فخسرت أربعة أشياء دفعةً:
زرّ الرجوع، و`aria-hidden` عن الفواصل فصار قارئُ الشاشة يقرأ «◂» بين كل
كلمتين، و`aria-current="page"`، و`aria-label` على `<nav>`.
"""

import pathlib
import re

TEMPLATES = pathlib.Path("templates")
COMPONENT = TEMPLATES / "components" / "breadcrumbs.html"

#: الجذر الذي يطبعه المكوّن بنفسه — فتمريره أباً يُكرّره.
ROOT_URL = "/dashboard/"


def _pages():
    for f in sorted(TEMPLATES.rglob("*.html")):
        if f == COMPONENT:
            continue
        yield f, f.read_text(encoding="utf-8")


def test_the_component_still_prints_the_root_itself():
    """لو كفّ عن طباعته لانقلب الحارس أدناه إلى ضدّه."""
    body = COMPONENT.read_text(encoding="utf-8")

    assert f'href="{ROOT_URL}"' in body
    assert "الرئيسية" in body


def test_no_page_passes_the_root_as_a_parent():
    duplicated = []
    for f, src in _pages():
        for i, line in enumerate(src.splitlines(), 1):
            if "breadcrumbs.html" in line and f'parent_url="{ROOT_URL}"' in line:
                duplicated.append(f"{f.as_posix()}:{i}")

    assert not duplicated, f"جذرٌ مُكرّر في: {duplicated}"


def test_every_breadcrumb_block_uses_the_component():
    """الصياغة اليدوية تخسر زرّ الرجوع وسمات الوصولية بلا أن تُخفق."""
    hand_rolled = []
    block = re.compile(r"{%\s*block breadcrumbs\s*%}(.*?){%\s*endblock", re.S)
    for f, src in _pages():
        for m in block.finditer(src):
            body = m.group(1)
            if not body.strip():
                continue
            if "components/breadcrumbs.html" not in body:
                hand_rolled.append(f.as_posix())

    assert not hand_rolled, f"شريطٌ مكتوبٌ باليد في: {hand_rolled}"


def test_the_component_carries_what_hand_rolling_drops():
    """ما تخسره الصياغة اليدوية — مذكورٌ هنا كي لا يُحذف من المكوّن سهواً."""
    body = COMPONENT.read_text(encoding="utf-8")

    assert 'data-action="back"' in body, "زرّ الرجوع"
    assert 'aria-current="page"' in body, "الصفحة الحالية لقارئ الشاشة"
    assert 'aria-label="مسار التصفح"' in body, "تسمية شريط التصفّح"
    assert body.count('aria-hidden="true"') >= 3, "الفواصل تُقرأ إن لم تُخفَ"

"""تبويب «متابعة الأداء المدرسي» في القائمة الرئيسية: أقسامٌ وبنودٌ للعرض فقط (W-20261124-005)."""

import pathlib
import re

from tests.css_source import read_css

BASE_HTML = pathlib.Path("templates/base/base.html").read_text(encoding="utf-8")
CSS = read_css()
ROLE_GUARD = 'role == "principal" or role == "vice_academic" or role == "vice_admin"'


def _menu() -> str:
    start = BASE_HTML.index('<div class="sd-menu sd-menu--cols-3" id="m-performance-follow-up"')
    return BASE_HTML[start : BASE_HTML.index("{% endif %}", start)]


def test_the_tab_button_follows_the_menu_button_pattern_and_is_role_gated():
    button = re.search(
        r'<button type="button" class="nb" id="btn-performance-follow-up".*?</button>',
        BASE_HTML,
        re.S,
    )
    assert button, 'زرُّ التبويب مفقود (وبـ type="button" كي لا يُرسل نموذجًا)'
    text = button.group(0)
    for part in (
        'data-sd="m-performance-follow-up"',
        'aria-expanded="false"',
        'aria-controls="m-performance-follow-up"',
        'class="chv"',
        '{% icon "trend" %}',
    ):
        assert part in text
    guard = BASE_HTML.rindex("{% if ", 0, button.start())
    assert ROLE_GUARD in BASE_HTML[guard : button.start()]
    assert "is_admin_role" not in BASE_HTML[guard : button.start()]


def test_the_menu_is_gated_by_the_same_roles():
    start = BASE_HTML.index('id="m-performance-follow-up"')
    assert ROLE_GUARD in BASE_HTML[BASE_HTML.rindex("{% if ", 0, start) : start]


def test_the_menu_lists_the_three_sections_and_two_direct_items_in_order():
    menu = _menu()
    labels = re.findall(r'<div class="sd-label">(.*?)</div>', menu)
    assert labels == ["القيادة العليا", "الكادر الأكاديمي", "الكادر الإداري"]
    items = re.findall(r'role="menuitem" aria-disabled="true">(.*?)<span', menu)
    assert items == [
        "النائب الإداري",
        "النائب الأكاديمي",
        "الزيارات الصفية",
        "البحث العلمي",
        "الحصص التبادلية",
        "الحصص المكتبية",
        "حصص المختبرات",
        "الإرشاد الأكاديمي",
        "مصادر التعلم",
        "التعليم الإلكتروني",
        "الاجتماعي",
        "النفسي",
        "منسق شؤون الطلاب",
        "الأقسام الإدارية",
        "الإشراف الإداري",
        "ملاحظو الباصات",
        "الاستقبال",
        "الخطط المدرسية",
        "متابعات الوزارة",
        "الأقسام الإدارية",
    ]
    assert menu.rindex("الخطط المدرسية") > menu.rindex("الاستقبال")
    # «الأقسام الإدارية» تظهر مرّتين: في «الكادر الإداري» وبندٍ مباشرٍ بعد «متابعات الوزارة»
    assert menu.count("الأقسام الإدارية") == 2
    assert menu.rindex("الأقسام الإدارية") > menu.rindex("متابعات الوزارة")


def test_the_items_are_display_only_not_links_and_say_they_are_coming():
    menu = _menu()
    assert "<a " not in menu and "href" not in menu and "onclick" not in menu
    assert "style=" not in menu
    assert menu.count('<span class="sr-only"> — قريبًا</span>') == 20


def test_the_display_only_style_is_defined_with_tokens_and_logical_properties():
    block = re.search(r"\.sd-item-soon \{(.*?)\}", CSS, re.S)
    assert block, "تنسيقُ البند النصّيّ غير معرَّف"
    assert "px" not in block.group(1)
    assert "cursor: default" in block.group(1)
    assert "left" not in block.group(1) and "right" not in block.group(1)
    assert ".sd-section--wide" in CSS

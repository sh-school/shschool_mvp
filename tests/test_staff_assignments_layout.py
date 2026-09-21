"""تخطيطُ صفحة التكليفات: أربعةُ أعمدةٍ بارتفاع النافذة، والقوائمُ تُمرَّر داخل بطاقتها لا الصفحة.

حارسٌ ساكنٌ على القالب وCSS (القياسُ الحيُّ بمتصفّحٍ حقيقيّ في وصف طلب الدمج): إن سقط
`page-noscroll` أو انفكّت الأعمدةُ الأربعة أو عاد الجدولُ ستّةَ أعمدة عاد التمريرُ الرأسيّ.
"""

import pathlib
import re

from tests.css_source import read_css

ROOT = pathlib.Path(__file__).resolve().parent.parent
PAGE = (ROOT / "templates/staff_affairs/assignments.html").read_text(encoding="utf-8")
ROWS = (ROOT / "templates/staff_affairs/partials/assignment_rows.html").read_text(encoding="utf-8")


def test_page_opts_into_no_page_scroll():
    assert "{% block main_class %}page-noscroll{% endblock %}" in PAGE


def test_cards_are_direct_grid_children_and_solo_when_no_form():
    assert "sa-assign__col" not in PAGE
    assert PAGE.count("{% section_card ") == 4
    assert "sa-assign--solo" in PAGE


def test_every_list_card_is_flush_so_it_scrolls_inside_itself():
    for title in ("قائمةٌ اليوم", "قادمة", "السجلّ"):
        line = next(ln for ln in PAGE.splitlines() if f'section_card "{title}' in ln)
        assert "flush=True" in line


def test_table_is_compact_four_columns():
    assert len(re.findall(r"<th[ >]", ROWS)) == 4
    assert "sa-cell-sub" in ROWS


def test_css_pins_columns_and_scrolls_bodies_inside_cards():
    css = read_css()
    assert ".sa-assign { grid-template-columns: repeat(4, minmax(0, 1fr)); }" in css
    assert "#main-content.page-noscroll > .exec-dash > .sa-assign" in css
    assert (
        ".sa-assign > .ui-section > .ui-section__body { flex: 1; min-height: 0; overflow: auto; }"
        in css
    )

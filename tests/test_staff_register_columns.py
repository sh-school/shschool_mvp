"""أعمدةُ سجلّ الكادر: الاسمُ سطرٌ واحد، ونسبُ الأعمدة مئةٌ في الحالتين — W-20261002-044.

كان اثنَي عشرَ عموداً بنسبٍ `nth-child` مجموعُها 99%: التفّ الاسمُ على سطرين في 39 صفّاً من 50 (قيس
على 1366×768)، وعمودُ «المغادرة» الثالثُ عشرُ عصر «الدخول» إلى 13px فطغى المحتوى بتمريرٍ أفقيّ.
فالعرضُ الآن بصنفٍ لكلّ عمود (`c-*`) والمجموعُ مئةٌ في الحالتين. وهذا الحارسُ نصّيّ (بلا متصفّح)؛
وقياسُ الاسم الفعليّ على 1366 و1280 في tests/e2e/test_staff_register_headers_live.py.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from tests.css_source import read_css
from tests.test_staff_register_screen import _body, _staff, principal, school  # noqa: F401

pytestmark = pytest.mark.django_db

ROOT = Path(__file__).resolve().parent.parent
_TEMPLATE = (ROOT / "templates" / "staff_affairs" / "_staff_table.html").read_text(encoding="utf-8")

# الأعمدةُ في الحالة العاديّة، وما يُضاف للمغادرين.
BASE_COLUMNS = ("name", "ids", "title", "dept", "contact", "place", "license", "joined", "login")
LEFT_EXTRA = ("left",)


def _widths(css: str, prefix: str) -> dict[str, int]:
    """نسبُ `.staff-register<prefix> .c-<col> { inline-size: N%; }` كما في الأنماط."""
    pattern = re.compile(
        r"\.staff-register" + re.escape(prefix) + r"\s+\.c-([a-z]+)\s*\{\s*inline-size:\s*(\d+)%;"
    )
    return {col: int(pct) for col, pct in pattern.findall(css)}


def _effective(css: str, with_left: bool) -> dict[str, int]:
    widths = _widths(css, "")
    if with_left:
        widths.update(_widths(css, "[data-left]"))
    return widths


class TestColumnWidthsAreOneHundred:
    def test_the_normal_state_sums_to_100(self):
        widths = _effective(read_css(), with_left=False)

        assert set(widths) == set(BASE_COLUMNS), widths
        assert sum(widths.values()) == 100, widths

    def test_the_left_state_sums_to_100_with_its_own_column(self):
        widths = _effective(read_css(), with_left=True)

        assert set(widths) == set(BASE_COLUMNS) | set(LEFT_EXTRA), widths
        assert sum(widths.values()) == 100, widths

    def test_no_width_is_written_by_position_any_more(self):
        """`nth-child` يُزاح بإضافة عمود — وهكذا عُصر عمودُ «الدخول» إلى 13px."""
        assert not re.search(r"\.staff-register\s+th:nth-child", read_css())

    def test_every_template_column_has_a_class_that_is_sized(self):
        used = set(re.findall(r'class="[^"]*\bc-([a-z]+)\b', _TEMPLATE))

        assert used == set(BASE_COLUMNS) | set(LEFT_EXTRA)

    def test_the_name_column_leaves_room_for_the_longest_name_at_1366(self):
        """≥ 300px عند 1366 من جدولٍ بعرض 1320px — أي 22% بحشوٍّ ناقصٍ منه: ما يتّسع لاسمٍ
        بالخطّ المعلن (0.875rem) والأطولُ في بيانات المدرسة نحو 240px."""
        name = _effective(read_css(), with_left=False)["name"]

        assert name * 1320 / 100 >= 285


class TestTheNameIsOneLine:
    def test_the_name_never_wraps_and_ends_with_dots_not_a_second_line(self):
        css = read_css()
        block = re.search(r"\.staff-register\s+\.staff-name\s*\{(.*?)\}", css, re.S)

        assert block, "لا قاعدةَ لاسم المنتسب في السجلّ"
        rules = block.group(1)
        assert "white-space: nowrap" in rules
        assert "text-overflow: ellipsis" in rules
        assert "font-size: var(--text-sm)" in rules, "الخطُّ بالرمز لا px"

    def test_the_full_name_is_in_the_title_for_the_clipped_case(self, client_as, school, principal):
        _staff(school, "اسمٌ طويلٌ جدّاً جدّاً جدّاً جدّاً جدّاً جدّاً", "29000000099")

        body = _body(client_as, principal)

        assert 'title="اسمٌ طويلٌ جدّاً جدّاً جدّاً جدّاً جدّاً جدّاً"' in body


class TestMergedColumnsKeepTheirSorts:
    @pytest.mark.parametrize(
        "key",
        ["employee", "national", "email", "residence", "nationality"],
    )
    def test_each_label_in_a_stacked_header_still_sorts_by_its_own_key(self, key):
        """العمودُ المركّبُ سطرانِ كلٌّ برابط فرزه — فلا يُفقد فرزٌ بالدمج."""
        assert f'"{key}"' in _TEMPLATE

    def test_the_phone_label_has_no_sort_link(self):
        assert re.search(r'sort_th_stack sort "" "الجوال"', _TEMPLATE)

    def test_the_stacked_header_renders_both_links_and_one_aria_sort(self, rf):
        from core.templatetags.sorting import sort_th_stack

        request = rf.get("/x/", {"sort": "national", "dir": "asc"})

        class State:
            key = "national"
            descending = False

            def starts_desc(self, key):
                return False

        html = sort_th_stack(
            {"request": request}, State(), "employee", "الرقم الوظيفي", "national", "الرقم الشخصي"
        )

        assert html.count('class="th-sort"') == 2
        assert "sort=employee" in html and "sort=national" in html
        assert html.count("aria-sort=") == 1
        assert 'aria-sort="ascending"' in html

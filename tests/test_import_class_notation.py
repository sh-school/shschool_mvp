"""[IMPORT] الاستيراد يفهم «7/1» كما يفهم عمودين منفصلين.

الشُّعب في المدرسة تُسمّى «7/1» و«11/2» — اسمٌ واحد لا حقلان. وكان
`_parse_import_row` يقرأ الصفّ من العمود الثاني والشعبة من الثالث. فملفٌّ
يحمل «7/1» في خانة الصف لا يُطابق مفتاحاً في `_IMPORT_GRADE_NORMALIZE`،
فيُنشأ الطالب **بلا تسجيل**.

ولا يُخفق الاستيراد: يُدرج سطراً في قائمة الأخطاء ويمضي. فيسهل أن يمرّ مئةُ
طالبٍ بلا شعبة دون أن ينتبه أحد — والملفّ «نجح».
"""

import pytest

from core.views_students import _split_class_notation


@pytest.mark.parametrize(
    ("cells", "expected"),
    [
        (("7", "1"), ("7", "1")),
        (("11", "2"), ("11", "2")),
        (("G12", "3"), ("G12", "3")),
    ],
)
def test_two_columns_pass_through_untouched(cells, expected):
    """الشكل القائم لا يتغيّر — والملفّات السابقة تبقى صالحة."""
    assert _split_class_notation(*cells) == expected


@pytest.mark.parametrize(
    ("cell", "expected"),
    [
        ("7/1", ("7", "1")),
        ("11/2", ("11", "2")),
        ("12/10", ("12", "10")),
        ("7.1", ("7", "1")),
        ("9-3", ("9", "3")),
        (" 10 / 4 ", ("10", "4")),
    ],
)
def test_a_single_cell_is_split(cell, expected):
    """تسمية المدرسة نفسها: «7/1»."""
    assert _split_class_notation(cell, "") == expected


def test_a_filled_section_column_wins_over_a_separator():
    """لو جاء العمودان معاً فالفصل صريحٌ ولا يُخمَّن."""
    assert _split_class_notation("7/1", "5") == ("7/1", "5")


@pytest.mark.parametrize("cell", ["7", "G11", ""])
def test_a_cell_without_a_separator_is_left_alone(cell):
    assert _split_class_notation(cell, "") == (cell, "")


def test_the_split_grade_matches_the_import_vocabulary():
    """القسمة بلا فائدة إن لم يُطابق الناتجُ قاموس التطبيع."""
    from core.views_students import _IMPORT_GRADE_NORMALIZE

    for cell, grade in (("7/1", "7"), ("11/2", "11"), ("12/3", "12")):
        head, _section = _split_class_notation(cell, "")
        assert head == grade
        assert _IMPORT_GRADE_NORMALIZE.get(head), f"{cell} → {head} لا يُطابق"


# ── نقطة الوصل ────────────────────────────────────────────────────────
#
# الاختبارات أعلاه تفحص المساعدة وحدها. ونزعُ استدعائها من `_parse_import_row`
# أبقاها كلَّها خضراء — أي أنها تحرس دالّةً لا ميزة. وهذه تسدّ ذلك.


def test_the_parser_actually_uses_the_split():
    """السطر الخام كما يصل من الملفّ — لا المساعدة معزولةً."""
    from core.views_students import _parse_import_row

    row = ("28812345678", "طالب الاختبار", "11/2", "", "", "", "", "", "", "", "")

    fields = _parse_import_row(row)

    assert (fields["grade_raw"], fields["section"]) == ("11", "2")


def test_the_parser_leaves_two_columns_as_they_are():
    from core.views_students import _parse_import_row

    row = ("28812345678", "طالب الاختبار", "9", "3", "", "", "", "", "", "", "")

    fields = _parse_import_row(row)

    assert (fields["grade_raw"], fields["section"]) == ("9", "3")

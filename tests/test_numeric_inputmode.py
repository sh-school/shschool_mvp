"""[MOBILE M-07] حقلُ الأرقام يفتح لوحةَ الأرقام على الجوال.

`type="number"` وحدَه لا يكفي: iOS يعرض لوحةَ المفاتيح كاملة، فيبحث المعلّمُ عن
الأرقام في كلّ درجةٍ يرصدها. و`inputmode` هو ما يطلبها — `decimal` لما يقبل كسراً
(الدرجات، الحرارة)، و`numeric` للأعداد الصحيحة (الحصص، الأيّام، الدقائق).

- الحقلُ المكتوبُ باليد يحمل `inputmode` في وسمه نفسِه.
- ووسمُ `{% field … type="number" %}` يضعه تلقائياً من `step` (مركزيّاً في `core/templatetags/ui.py`).
- وودجةُ Django المرسومةُ للمستخدم (`breach`) تحمله في سماتها.
"""

import re
from pathlib import Path

import pytest
from django.template import Context, Template

from core.templatetags.ui import number_inputmode

TEMPLATES = Path(__file__).resolve().parent.parent / "templates"
INPUT = re.compile(r"<input\b[^>]*>", re.S)


def test_every_hand_written_number_input_asks_for_the_numeric_keyboard():
    missing = []
    for path in sorted(TEMPLATES.rglob("*.html")):
        for tag in INPUT.findall(path.read_text(encoding="utf-8")):
            if re.search(r'type="number"', tag) and "inputmode=" not in tag:
                missing.append(f"{path.relative_to(TEMPLATES)}: {' '.join(tag.split())[:120]}")
    assert not missing, "حقلُ أرقامٍ بلا inputmode — لوحةٌ كاملةٌ على iOS:\n" + "\n".join(missing)


@pytest.mark.parametrize(
    ("step", "mode"),
    [
        (None, "numeric"),
        ("1", "numeric"),
        ("0.1", "decimal"),
        ("0.5", "decimal"),
        ("any", "decimal"),
    ],
)
def test_the_mode_follows_the_step(step, mode):
    assert number_inputmode(step) == mode


def _render(source):
    return Template("{% load ui %}" + source).render(Context())


def test_the_field_tag_adds_the_keyboard_to_a_number_field():
    html = _render('{% field "temperature" "الحرارة" type="number" step="0.1" %}')
    assert 'inputmode="decimal"' in html

    html = _render('{% field "capacity" "الطاقة" type="number" %}')
    assert 'inputmode="numeric"' in html


def test_an_explicit_mode_is_kept_and_other_types_are_untouched():
    assert 'inputmode="tel"' in _render('{% field "p" "هاتف" type="tel" inputmode="tel" %}')
    assert "inputmode" not in _render('{% field "t" "عنوان" %}')


def test_the_breach_count_widget_asks_for_numbers():
    from breach.forms import BreachReportForm

    assert BreachReportForm.base_fields["affected_count"].widget.attrs["inputmode"] == "numeric"

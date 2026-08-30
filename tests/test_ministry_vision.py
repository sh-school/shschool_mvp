"""[BRAND] رؤية الوزارة — نصٌّ واحدٌ في كل مطبوعة.

كان في هذا الموضع نصٌّ كتبتُه في جلسةٍ سابقة بلا مصدر («تعليم ريادي مبتكر
لمجتمع واعٍ ومنتج»)، وهو يخالف نصَّ الرؤية في تذييل مطبوعات المدرسة. سألت
المدرسةُ عنه واعتمدت نصَّها.

ونصٌّ يُنسب إلى وزارةٍ يُؤخذ عنها لا يُصاغ. وهو مصدرٌ واحد يُضمَّن حيث
يلزم، فتعديلُه يُصيب المطبوعات كلَّها لا بعضها.
"""

import pathlib

import pytest
from django.template.loader import render_to_string

#: النصّ الذي اعتمدته المدرسة.
VISION = "الريادة في توفير فرص تعلم دائمة ومبتكرة وذات جودة عالية للمجتمع القطري"

#: ما كان مكتوباً بلا سند.
UNSOURCED = "تعليم ريادي مبتكر"


def test_the_component_carries_the_adopted_text():
    assert render_to_string("components/ministry_vision.html").strip() == VISION


def test_the_unsourced_wording_is_gone_from_every_template():
    """لو بقي في قالبٍ واحد لخرجت وثيقةٌ بنصٍّ وأخرى بغيره."""
    stray = [
        str(f)
        for f in pathlib.Path("templates").rglob("*.html")
        if UNSOURCED in f.read_text(encoding="utf-8")
    ]

    assert not stray, "نصٌّ بلا مصدر باقٍ في:\n" + "\n".join(stray)


@pytest.mark.parametrize(
    "template",
    [
        "templates/base/base.html",
        "templates/behavior/pdf/base_form.html",
        "templates/behavior/pdf/policy_doc.html",
        "templates/reports/base_qatar_report.html",
        "templates/schedule/print_schedule.html",
    ],
)
def test_each_footer_includes_the_one_source(template):
    """لا يُكتب النصّ في قالبٍ نصّاً — فتعديلُه يومَها يُصيب بعضها دون بعض."""
    src = pathlib.Path(template).read_text(encoding="utf-8")

    assert "components/ministry_vision.html" in src
    assert VISION not in src, "يُضمَّن ولا يُنسخ"

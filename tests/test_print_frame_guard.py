"""[PRINT] حارسُ الإطار المطبوع المركزيّ: لا ترويسةَ ولا تذييلَ جارياً خارجَ المكوّن، وسقّاطةٌ تنزل بترحيل القوالب (المواصفة ٥-٤).

الحارسُ نصّيٌّ سريعٌ يعمل في كلّ طلب دمج. ما يقيسه هو **المُعلَن**؛ أمّا **المرسوم** (أنّ التذييل صفٌّ واحدٌ وأنّ الخطَّ لا ينزل عن حدّه)
فيقيسه `tests/test_print_frame_render.py` بتخطيط WeasyPrint نفسِه على المكوّن.
"""

import pytest

from tests import print_frame_ratchet as ratchet


@pytest.mark.parametrize("kind", ["positions", "footer_classes"])
def test_no_template_grows_its_own_header_or_footer(kind):
    """`running(` و`@bottom-` وأصنافُ التذييل خارجَ المكوّن لا تزيد — ملفٌّ جديدٌ بها يسقط، والقديمُ بسقّاطةٍ."""
    grew, _ = ratchet.compare(kind)
    assert not grew, (
        "نسخةٌ جديدةٌ من ترويسة/تذييل PDF — استعمل `{% print_frame_css %}` و`{% print_frame_header %}` و`{% print_frame_footer %}` "
        f"(core/print_frame.py، المواصفة ٥): {grew}"
    )


@pytest.mark.parametrize("kind", ["positions", "footer_classes"])
def test_a_drop_is_recorded_so_it_is_not_spent_later(kind):
    _, dropped = ratchet.compare(kind)
    assert not dropped, f"نقصت نسخٌ ({dropped}) — أحسنت؛ اخفض tests/print_frame_baseline.json بـ`python -m tests.print_frame_ratchet --update` في هذا الطلب"


def test_the_baseline_starts_at_the_spec_count_of_fourteen_positions():
    """خطُّ الأساس اليومَ 14 موضعاً في 5 ملفّات (المواصفة ١-٥) — ينزل ولا يزيد أبداً."""
    positions = ratchet.baseline()["positions"]
    assert sum(positions.values()) <= 14 and len(positions) <= 5, positions


def test_the_central_component_may_define_them():
    """المكوّنُ نفسُه مستثنًى — وإلّا ما وُجد مكانٌ يُعرَّف فيه الإطار."""
    for allowed in ratchet.ALLOWED:
        assert (ratchet.ROOT / allowed).exists(), allowed

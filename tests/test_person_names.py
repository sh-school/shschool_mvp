"""اختصارُ اسم الشخص للعرض — أسماءٌ مصطنعةٌ فقط (لا أسماءَ حقيقيّةً في المستودع).

القاعدةُ في `core/person_names.py`: وحداتٌ لا كلمات، ومقطعان لمن له ثلاثُ وحداتٍ فأكثر، والتصادمُ يُفضّ على القائمة بحرفٍ لا بوحدةٍ ثالثة.
"""

import pytest

from core.person_names import name_units, short_name, short_names


@pytest.mark.parametrize(
    ("full", "expected"),
    [
        # عبد X وحدةٌ واحدة — لا «عبد الكواري»
        ("عبد الله محمد احمد الكواري", "عبد الله الكواري"),
        ("عبدالله محمد احمد الكواري", "عبدالله الكواري"),
        ("محمد عبد الرحمن خالد الملا", "محمد الملا"),
        # أبو/بن/آل
        ("خالد ابو بكر علي السيد", "خالد السيد"),
        ("خالد أبو بكر علي السيد", "خالد السيد"),
        ("يوسف محمد بن علي الكواري", "يوسف الكواري"),
        ("علي محمد سعد آل ثاني", "علي آل ثاني"),  # لا «علي ثاني»
        # X الله / X الدين
        ("لطف الله محمد علي الاحزم", "لطف الله الاحزم"),
        ("سيف الدين احمد محمد يوسف", "سيف الدين يوسف"),
        ("سعد سيف الدين علي", "سعد علي"),
        # أوغلو تلتصق بالسابقة — لا «أوغلو» وحدَها
        ("محمد علي يلماز اوغلو", "محمد يلماز اوغلو"),
        ("محمد علي يلماز أوغلو", "محمد يلماز أوغلو"),
        # ثلاثُ وحداتٍ ← مقطعان
        ("احمد علي حسن", "احمد حسن"),
        ("محمد عبد الله الكواري", "محمد الكواري"),
        # وحدتان فأقلّ: كما هي
        ("محمد عبد الله", "محمد عبد الله"),
        ("علي بن محمد", "علي بن محمد"),
        ("محمد يلماز اوغلو", "محمد يلماز اوغلو"),
        ("سعد", "سعد"),
        # مسافاتٌ زائدة تُوحَّد
        ("  احمد   علي   حسن ", "احمد حسن"),
        ("", ""),
    ],
)
def test_the_short_name_is_the_first_and_last_unit(full, expected):
    assert short_name(full) == expected


def test_compound_words_are_one_unit():
    assert name_units("عبد الله محمد ابو بكر آل ثاني") == ["عبد الله", "محمد", "ابو بكر", "آل ثاني"]
    assert name_units("لطف الله سيف الدين") == ["لطف الله", "سيف الدين"]


def test_the_tashkeel_and_alef_forms_do_not_change_the_match_nor_the_displayed_name():
    """المطابقةُ على صورةٍ مطبَّعة، والعرضُ بحروف صاحبه كما كُتبت."""
    assert short_name("عَبْد اللّه محمد احمد الكواري") == "عَبْد اللّه الكواري"
    assert short_name("ابي بكر محمد علي خالد") == "ابي بكر خالد"


class TestCollisionsAreResolvedOnTheList:
    def test_two_different_people_with_the_same_short_name_get_the_middle_initial(self):
        names = ["محمد علي حسن", "محمد سعد حسن", "خالد يوسف عمر"]

        assert short_names(names) == ["محمد ع. حسن", "محمد س. حسن", "خالد عمر"]

    def test_a_clash_the_initial_cannot_break_falls_back_to_the_full_name(self):
        names = ["محمد علي حسن", "محمد عمر حسن"]  # الحرفُ الأوّلُ من الوحدة الثانية واحدٌ (ع)

        assert short_names(names) == names

    def test_the_same_person_twice_is_not_a_clash(self):
        assert short_names(["احمد علي حسن", "احمد علي حسن"]) == ["احمد حسن", "احمد حسن"]

    def test_the_order_and_length_are_kept_and_unclashing_names_are_untouched(self):
        names = ["سعد", "احمد علي حسن", "محمد عبد الله"]

        assert short_names(names) == ["سعد", "احمد حسن", "محمد عبد الله"]

    def test_an_empty_list_is_empty(self):
        assert short_names([]) == []

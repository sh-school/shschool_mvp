"""[CURRICULUM] الشعبة الثانوية تحمل مسارها.

طالب الصف العاشر الناجح يختار في المرحلة التالية بين ثلاثة مسارات:

    علمي  ·  آداب وإنسانيات  ·  تكنولوجي

ولم يكن في `ClassGroup` ما يحملها: `grade` و`section` و`level_type`
(إعدادي/ثانوي) وحدها. فالمخرج الوحيد أن يُدسّ المسار في `section` نصّاً
(«علمي-١»)، وحينها لا يفهمه النظام: لا ترشيحَ بالمسار، ولا خططَ دراسية
تختلف باختلافه، ولا تقاريرَ حسبه — ولا يعرف أحدٌ أن «علمي-١» و«علمي-٢»
مسارٌ واحد.

والحقل فارغٌ افتراضاً: الإعدادي والعاشر بلا مسار، والشعبة الثانوية قبل
تحديد مسارها حالةٌ مشروعة.
"""

import pytest
from django.core.exceptions import ValidationError

from core.models import ClassGroup


@pytest.fixture
def sec(db, school):
    def _make(**kw):
        defaults = {
            "school": school,
            "grade": "G11",
            "section": "1",
            "level_type": "sec",
        }
        return ClassGroup(**{**defaults, **kw})

    return _make


def test_the_three_tracks_are_the_ones_the_school_offers():
    labels = dict(ClassGroup.TRACKS)

    assert labels == {
        "science": "علمي",
        "humanities": "آداب وإنسانيات",
        "technology": "تكنولوجي",
    }


@pytest.mark.parametrize("track", ["science", "humanities", "technology"])
def test_a_secondary_section_may_carry_any_of_them(sec, track):
    group = sec(track=track)
    group.full_clean()

    assert group.track == track


def test_a_section_without_a_track_is_legitimate(sec):
    """قبل تحديد المسار — ولا يُجبَر المُدخِل على اختيارٍ لم يُتّخذ بعد."""
    group = sec()

    group.full_clean()

    assert group.track == ""


def test_a_preparatory_section_may_not_carry_a_track(db, school):
    """المسار للثانوي وحده — ومن أخطأ يُخبَر لا يُرفض بلا بيان."""
    group = ClassGroup(school=school, grade="G8", section="1", level_type="prep", track="science")

    with pytest.raises(ValidationError) as exc:
        group.full_clean()

    assert "track" in exc.value.error_dict


def test_the_display_name_says_the_track(sec):
    """‏«الحادي عشر / ١» وحدها لا تُميّز العلميّ من الأدبيّ في أيّ قائمة."""
    group = sec(track="science", academic_year="2026-2027")

    assert "علمي" in str(group)


def test_the_display_name_stays_clean_without_one(sec):
    group = sec(academic_year="2026-2027")

    assert "—" not in str(group)


def test_the_admin_shows_and_filters_by_track():
    """حقلٌ لا يُرى في اللوحة لا يُدخَل ولا يُراجَع."""
    from core.admin import ClassGroupAdmin

    assert "track" in ClassGroupAdmin.list_display
    assert "track" in ClassGroupAdmin.list_filter

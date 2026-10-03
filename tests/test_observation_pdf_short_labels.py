"""[QUALITY] استمارةُ الزيارة الصفّيّة المطبوعة: رموزٌ مختصرة في جدول المعلومات الأساسيّة (W-20261002-016).

بطلب المالك: الشعبةُ «11/2» (صفّ/شعبة) فقط، والزائرُ والمعلّمُ بأوّل مقطعٍ وآخرِ مقطع — ذاتُ ما يُعرض في الجدول العامّ
(`core.person_names.short_name` و`ClassGroup.short_label`). والوصفُ الكاملُ للشعبة والاسمُ الكاملُ يبقيان في القاعدة والتدقيق،
والاسمُ الكاملُ في ختم التوقيع الإلكترونيّ (وثيقةُ توقيعٍ لا خانةُ عرض).
"""

import pytest

from tests.test_observation_pdf_form import (  # noqa: F401 — أجهزةُ الاستمارة نفسُها
    VISITOR_NAME,
    _acknowledged,
    _html_of,
    criteria,
    named,
    observation,
)

pytestmark = pytest.mark.django_db


def _with_class(obs, grade="G11", section="2", track="science"):
    from core.models import ClassGroup

    obs.class_group = ClassGroup.objects.create(
        school=obs.school,
        grade=grade,
        section=section,
        level_type="sec",
        track=track,
        academic_year="2026-2027",
    )
    obs.save()
    return obs


def test_the_class_is_printed_as_grade_slash_section_only(named):
    obs = _with_class(named)

    html = _html_of(obs)

    assert "11/2" in html
    assert str(obs.class_group) not in html, "الوصفُ الكاملُ بالمسار والعام لا يُطبع في الخانة"
    assert "(2026-2027)" not in html


def test_an_observation_without_a_class_prints_an_empty_cell(named):
    html = _html_of(named)

    assert "None" not in html


def test_the_visitor_and_the_teacher_print_first_and_last_unit_only(named):
    """«سالم الزائر الأوّل» ← «سالم الأوّل» و«ناصر المعلّم الأوّل» ← «ناصر الأوّل» في جدول المعلومات."""
    html = _html_of(named)

    assert "سالم الأوّل" in html and "ناصر الأوّل" in html
    assert "سالم الزائر الأوّل" not in html and "ناصر المعلّم الأوّل" not in html


def test_compound_names_stay_whole_units(observation):
    """«عبد الله» و«آل ثاني» وحدتان لا كلمتان: لا يخرج «عبد الكواري» ولا «محمد ثاني»."""
    observation.observer.full_name = "عبد الله محمد سعد الكواري"
    observation.observer.save(update_fields=["full_name"])
    observation.teacher.full_name = "محمد سعد آل ثاني"
    observation.teacher.save(update_fields=["full_name"])

    html = _html_of(observation)

    assert "عبد الله الكواري" in html
    assert "محمد آل ثاني" in html


def test_the_full_name_stays_in_the_electronic_signature_stamp(named):
    """ختمُ التوقيع وثيقةُ توقيعٍ: يحمل الاسمَ الكاملَ كما كان، لا الرمزَ المختصر."""
    html = _html_of(_acknowledged(named))

    assert f"<div>{VISITOR_NAME}</div>" in html

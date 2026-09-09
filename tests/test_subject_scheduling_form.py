"""[SCHEDULE] قيودُ الموادّ في الجدول: زرٌّ واحدٌ في الذيل لا زرّان في كلّ سطر.

كان لكلّ مادّةٍ زرُّ حفظٍ لنطاق «أيّامٍ مختلفة» وزرُّ قلبٍ للازدواج، فمراجعةُ
عشرين مادّةً عشرون رحلةً إلى الخادم — والقرارُ في ذهن النائب واحد. فصار
الجدولُ نموذجاً واحداً وزرّاً واحداً، والخادمُ يحفظ ما تغيّر وحدَه.
"""

import pytest
from django.test import Client
from django.urls import reverse

from operations.models import Subject
from tests.conftest import MembershipFactory, RoleFactory, UserFactory

pytestmark = pytest.mark.django_db

YEAR = "2026-2027"


@pytest.fixture
def subjects(school):
    return [
        Subject.objects.create(school=school, name_ar="الفنّيّة", code="ART"),
        Subject.objects.create(school=school, name_ar="التكنولوجيا", code="TECH"),
    ]


def _vice(school):
    user = UserFactory(full_name="النائب الأكاديميّ")
    MembershipFactory(
        user=user, school=school, role=RoleFactory(school=school, name="vice_academic")
    )
    client = Client()
    client.force_login(user)
    return client


def _save(client, data):
    return client.post(reverse("save_subject_scheduling"), data, follow=True, HTTP_HOST="localhost")


def test_one_button_saves_both_columns_for_every_row(school, subjects):
    art, tech = subjects

    _save(
        _vice(school),
        {"double": [str(art.pk)], f"scope_{art.pk}": "none", f"scope_{tech.pk}": "sec"},
    )

    art.refresh_from_db()
    tech.refresh_from_db()
    assert (art.requires_double_period, art.spread_days_scope) == (True, "none")
    assert (tech.requires_double_period, tech.spread_days_scope) == (False, "sec")


def test_an_unticked_box_turns_the_double_off(school, subjects):
    """المربّعُ غيرُ المؤشَّرِ لا يُرسَل — والغيابُ هنا قرارٌ لا سهو."""
    art, _ = subjects
    art.requires_double_period = True
    art.save(update_fields=["requires_double_period"])

    _save(_vice(school), {f"scope_{art.pk}": "none"})

    art.refresh_from_db()
    assert art.requires_double_period is False


def test_an_unknown_scope_is_refused_and_the_row_keeps_its_value(school, subjects):
    art, _ = subjects
    art.spread_days_scope = "sec"
    art.save(update_fields=["spread_days_scope"])

    response = _save(_vice(school), {f"scope_{art.pk}": "المرّيخ"})

    art.refresh_from_db()
    assert art.spread_days_scope == "sec"
    assert "نطاقٌ غيرُ معروف" in response.content.decode()


def test_nothing_changed_says_so(school, subjects):
    art, tech = subjects

    response = _save(_vice(school), {f"scope_{art.pk}": "none", f"scope_{tech.pk}": "none"})

    assert "لا تغييرَ يُحفظ" in response.content.decode()


def test_a_subject_of_another_school_is_untouched(school, subjects):
    """الحلقةُ تدور على موادّ مدرسةِ المُدخِل وحدَها."""
    from tests.conftest import SchoolFactory

    other = SchoolFactory()
    theirs = Subject.objects.create(school=other, name_ar="الفنّيّة", code="ART")

    _save(_vice(school), {"double": [str(theirs.pk)], f"scope_{theirs.pk}": "all"})

    theirs.refresh_from_db()
    assert (theirs.requires_double_period, theirs.spread_days_scope) == (False, "none")


def test_a_teacher_may_not_save_subject_constraints(school, subjects):
    art, _ = subjects
    teacher = UserFactory(full_name="معلّم")
    MembershipFactory(user=teacher, school=school, role=RoleFactory(school=school, name="teacher"))
    client = Client()
    client.force_login(teacher)

    _save(client, {"double": [str(art.pk)], f"scope_{art.pk}": "all"})

    art.refresh_from_db()
    assert art.requires_double_period is False


# ── حارسُ الاستحالة: تباعدٌ لا تسعه أيّامُ الأسبوع ────────────────────


def _assign(school, class_group, subject, periods):
    from operations.models import SubjectClassAssignment

    return SubjectClassAssignment.objects.create(
        school=school,
        class_group=class_group,
        subject=subject,
        weekly_periods=periods,
        academic_year=YEAR,
    )


@pytest.fixture
def crowded_class(school):
    """شعبةٌ ثانويّةٌ تطلب ستَّ حصصٍ من مادّة — فوق ما تسعه خمسةُ أيّام."""
    from tests.conftest import ClassGroupFactory

    return ClassGroupFactory(school=school, grade="G10", level_type="sec", academic_year=YEAR)


def test_an_impossible_spread_is_refused_at_save(school, subjects, crowded_class):
    """ستُّ حصصٍ لا تتباعد في خمسة أيّام — والاستحالةُ تُقال هنا لا بعد التوليد."""
    art, _ = subjects
    _assign(school, crowded_class, art, 6)

    response = _save(_vice(school), {f"scope_{art.pk}": "all", "year": YEAR})

    art.refresh_from_db()
    assert art.spread_days_scope == "none"
    body = response.content.decode()
    assert "يستحيل" in body and crowded_class.short_code in body


def test_a_scope_that_misses_the_crowded_level_passes(school, subjects, crowded_class):
    """الشعبةُ المزدحمةُ ثانويّةٌ، فنطاقُ الإعداديّ لا يمسّها — وهو الحلُّ نفسُه
    الذي أعاد الجدولَ إلى 871/871 يوم 2026-09-09."""
    art, _ = subjects
    _assign(school, crowded_class, art, 6)

    _save(_vice(school), {f"scope_{art.pk}": "prep", "year": YEAR})

    art.refresh_from_db()
    assert art.spread_days_scope == "prep"


def test_five_periods_still_fit(school, subjects, crowded_class):
    art, _ = subjects
    _assign(school, crowded_class, art, 5)

    _save(_vice(school), {f"scope_{art.pk}": "all", "year": YEAR})

    art.refresh_from_db()
    assert art.spread_days_scope == "all"


def test_the_double_is_saved_even_when_the_scope_is_refused(school, subjects, crowded_class):
    """المردودُ هو النطاقُ وحدَه — لا يسقط معه قرارُ الازدواج في السطر نفسِه."""
    art, _ = subjects
    _assign(school, crowded_class, art, 6)

    _save(_vice(school), {"double": [str(art.pk)], f"scope_{art.pk}": "all", "year": YEAR})

    art.refresh_from_db()
    assert (art.requires_double_period, art.spread_days_scope) == (True, "none")


def test_an_untouched_impossible_scope_is_not_re_flagged(school, subjects, crowded_class):
    """حالةٌ قائمةٌ في القاعدة لا تُعاد رسالةً كلَّما حُفظت الشاشة."""
    art, tech = subjects
    _assign(school, crowded_class, art, 6)
    art.spread_days_scope = "all"
    art.save(update_fields=["spread_days_scope"])

    response = _save(
        _vice(school), {f"scope_{art.pk}": "all", f"scope_{tech.pk}": "sec", "year": YEAR}
    )

    assert "يستحيل" not in response.content.decode()
    art.refresh_from_db()
    assert art.spread_days_scope == "all"

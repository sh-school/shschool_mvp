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

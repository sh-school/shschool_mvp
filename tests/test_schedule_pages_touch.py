"""صفحاتُ الجداول على آيفون وشاشات اللمس: لا إطار أصلاً، بل جدولٌ عاديّ.

كانت الورقةُ — عشراتُ صفحاتٍ بعرض A4 — في إطارٍ مضمَّن، فظهرت على آيفون (التطبيقُ
المثبَّت) صفحةً بيضاءَ بلا جداول، والخادمُ يرسمها كاملة. فكان الإطارُ لا يُحمَّل
على الهاتف واللمس، ويقوم مقامَه زرّان — رقعةٌ فوق المشكلة لا حلٌّ لها.

والحلُّ (قرارُ 2026-09-18، نفسُ فصل جدول المعلم المفرد): العرضُ الأساسيُّ جدولٌ
عاديٌّ في الصفحة نفسها — لا إطار، فلا مشكلةَ توافقٍ تُستثنى شاشةٌ من أجلها. وبقي
الإطارُ للطباعة والتنزيل وحدَهما، مخفيّاً دائماً على كلّ شاشة، يُحمَّل عند أوّل
طلب طباعةٍ لا فوراً.
"""

import re
from datetime import time
from pathlib import Path

import pytest
from django.urls import reverse

from operations.models import ScheduleSlot, Subject
from tests.conftest import ClassGroupFactory

pytestmark = pytest.mark.django_db

ROOT = Path(__file__).resolve().parent.parent
TEMPLATE = ROOT / "templates" / "schedule" / "pages_view.html"
YEAR = "2026-2027"


def _template():
    return TEMPLATE.read_text(encoding="utf-8")


def test_the_frame_has_no_src_until_the_script_decides():
    iframe = re.search(r"<iframe[^>]*>", _template()).group(0)
    assert " src=" not in iframe, "إطارٌ بـsrc يُحمَّل فوراً على كلّ شاشة"
    assert "data-src=" in iframe


def test_the_frame_is_hidden_on_every_screen_not_touch_alone():
    """لا استثناءَ لشاشةٍ بعينها — الإطارُ مخفيٌّ دائماً، والجدولُ هو المعروض."""
    assert "schedule-print-frame-hidden" in _template()
    assert "matchMedia" not in _template(), "لا حاجةَ لتمييز اللمس بعد أن صار الجدولُ نفسَه المعروض"


def test_touch_screens_get_the_real_table_not_a_blank_frame(client, school, principal_user):
    """لا فرقَ بين آيفون وحاسوب: الجدولُ في الصفحة نفسها من أوّل ردٍّ من الخادم."""
    subject, _ = Subject.objects.get_or_create(school=school, name_ar="الرياضيات", code="MAT")
    group = ClassGroupFactory(school=school, grade="G8", level_type="prep", academic_year=YEAR)
    ScheduleSlot.objects.create(
        school=school,
        class_group=group,
        teacher=principal_user,
        subject=subject,
        day_of_week=0,
        period_number=1,
        start_time=time(7, 30),
        end_time=time(8, 15),
        academic_year=YEAR,
        is_active=True,
    )
    client.force_login(principal_user)

    body = client.get(reverse("schedule_pages"), {"kind": "classes", "year": YEAR}).content.decode()

    # الجدولُ ذاتُه في نصّ الصفحة — لا إطارٌ ولا زرّان بديلان يُنتظر منهما فتحُه.
    assert "week-grid" in body
    assert "pages-screen" in body

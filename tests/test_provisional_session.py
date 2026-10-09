"""الرصدُ بحصّةٍ مؤقّتة للمعلّم (W-20261005-006، D-217م وD-218م): خدمةُ الإنشاء ومساراتُها ومفتاحُ التشغيل.

المعلّمُ ينشئ لشُعب إسناده فقط وفي اليوم الدراسيّ الجاري فقط (404 لا 403)، برقمِ حصّةٍ 1–7 وزمنٍ من `TimeSlotConfig`، ومفتاحُ
`PROVISIONAL_SESSIONS_ENABLED` يعزل الميزةَ كلَّها (مطفأً: لا مسارَ ولا زرّ ولا إنشاء). والمؤقّتةُ تُغلق ولا تُحذف.
"""

import datetime as dt
import re

import pytest
from django.urls import reverse
from django.utils import timezone

from operations.models import Subject, SubjectClassAssignment
from tests.attendance_fixtures import *  # noqa: F401,F403
from tests.attendance_fixtures import SUNDAY

FRIDAY = SUNDAY + dt.timedelta(days=5)

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _flag_on_and_today_is_sunday(settings, monkeypatch):
    settings.PROVISIONAL_SESSIONS_ENABLED = True
    monkeypatch.setattr(timezone, "localdate", lambda *a, **k: SUNDAY)


@pytest.fixture
def subject(school):
    return Subject.objects.create(school=school, name_ar="العلوم", code="SCI")


@pytest.fixture
def assigned(school, year, klass, teacher, subject, band, bells):
    """معلّمٌ مُسنَدةٌ إليه الشعبةُ، وجرسُها `ground` بثلاث حصص (1 و2 و3)."""
    type(klass).objects.filter(pk=klass.pk).update(time_band=band)
    klass.refresh_from_db()
    SubjectClassAssignment.objects.create(
        school=school,
        class_group=klass,
        subject=subject,
        teacher=teacher,
        weekly_periods=2,
        academic_year=year,
    )
    return klass


# ── الواجهة: المنتقي فوق قائمة الطلبة، 404 لغير المُسنَد، والمفتاح المطفأ ──


# ── المفتاحُ مطفأ ← السلوكُ السابق حرفاً (قيدُ المالك D-218م: الإضافةُ لا الحذفُ ولا التعديل) ──

#: وحدهنّ تذكرنَ المفتاحَ أو خدمتَه؛ ما سواهنّ (التوليدُ والجدولُ والتبديلُ والتعويضُ والرصدُ المبنيُّ على الحصص المجدولة) **لا يقرأ المفتاحَ أبداً**
#: فلا شيءَ فيها يتغيّر مطفأً ولا مشغَّلاً.
KEY_READERS = {
    "shschool/settings/base.py",
    "operations/services/provisional_session.py",
    "operations/views_provisional.py",
    "operations/templatetags/provisional_door.py",  # وسمُ القالب لزرّ جدول المعلّم (لا سياقَ في العرض)
    "operations/urls.py",  # مساراتُ الميزة
    "operations/admin.py",  # عمودُ القائمة وترشيحُها
    "operations/signals.py",  # إشارةُ إغلاق المؤقّتة عند حقيقيّةٍ جديدة (بالمفتاح وحدَه)
    "operations/services/class_grid.py",  # جدولُ الشعبة العموديّ: ميزةُ المفتاح نفسِه (W-20261006-005)
    "operations/views_class_grid.py",  # واجهةُ الجدول — ترجمةٌ إلى HTTP فقط
}


# ── جدولُ «حصصي اليوم» مُعطَّلٌ بمفتاح الحصّة المؤقّتة (أمرُ المالك، W-20261005-006) ──


def _schedule_page(client, user):
    return client.get(reverse("teacher_schedule")).content.decode()


def _anchors_to(page, *names):
    """كلُّ وسوم <a> في الصفحة إلى هذه المسارات (بأسمائها) — لمعرفة هل عطّلها `inert`."""
    urls = [reverse(n) for n in names]
    return [tag for tag in re.findall(r"<a [^>]*>", page) if any(f'href="{u}' in tag for u in urls)]


def test_leadership_view_of_the_schedule_is_untouched_by_the_switch(
    client_as, assigned, session, principal_user
):
    page = client_as(principal_user).get(reverse("teacher_schedule")).content.decode()

    assert "sessions-off-note" not in page and "is-off" not in page


# ── الصفحةُ الرئيسيّةُ للمعلّم (D-227م): تُخفى حصصُه من جدول المنصّة وتحلّ بطاقةُ «رصدُ الغياب (مؤقّت)» ──


# ── صفحةُ الشعبة بشبكة الكشف نفسِها (D-229م، D-16 layout-sheet) ──


# ── الجدولُ الأسبوعيّ للمعلّم: يُفتح مُطفأً كلُّ شيءٍ فيه و«تحت الإجراء» (D-231م) ──


def test_the_under_action_note_is_centered_triple_size_and_glowing_red():
    """أمرُ المالك: «تحت الإجراء» وسطَ السطر وأكبرَ 300% وبالأحمر المتوهّج."""
    from tests.css_source import read_css

    css = read_css()
    rule = css[css.index(".sessions-off-note {") :].split("}", 1)[0]

    assert "text-align: center" in rule
    assert "calc(var(--text-sm) * 3)" in rule
    assert "var(--status-danger-fg)" in rule and "text-shadow" in rule

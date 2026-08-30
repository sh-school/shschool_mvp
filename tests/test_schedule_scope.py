"""[SECURITY] جدولُ المعلّم له وحده — عرضاً وطباعة.

طُلب فحصُ صلاحيات المعلّم، فبدأ السؤال بـ«هل يطبع جدوله؟» — وكان الجواب
لا: زرُّ الطباعة معروضٌ له في صفحة الجدول، والمسارُ يردّه بـ403.

وكشف الفحصُ ما هو أخطر: `?teacher=` و`?class=` كانا يُقرآن لكلّ من طلبهما.
فأيُّ معلّمٍ يقرأ جدول زميله وجدول أيّ شعبةٍ بتغيير رقمٍ في الرابط —
والقصدُ المكتوب في وصف الدالّة خلافُه: «للمعلم أو كل المعلمين للمدير».

وفي الطباعة كان أوسع: `get_object_or_404(CustomUser, id=…)` بلا قيد
مدرسة — أي جدولُ معلّمٍ في مدرسةٍ أخرى.
"""

import pytest
from django.test import Client
from django.urls import reverse

from core.models import CustomUser
from core.models.access import Membership, Role
from operations.views_schedule import SCHEDULE_BROWSE_ROLES


@pytest.fixture
def person(db, school):
    def _make(name, role_name):
        user = CustomUser.objects.create(
            national_id=f"286{abs(hash(name)) % 10**8:08d}", full_name=name
        )
        role, _ = Role.objects.get_or_create(school=school, name=role_name)
        Membership.objects.create(user=user, school=school, role=role)
        return user

    return _make


def _client(user):
    c = Client()
    c.force_login(user)
    return c


def _get(user, name, query=""):
    return _client(user).get(reverse(name) + query, HTTP_HOST="localhost")


# ── المعلّم يطبع جدوله ───────────────────────────────────────────────


def test_a_teacher_may_print_their_own_timetable(db, person):
    """كان يُردّ بـ403 وزرُّ الطباعة معروضٌ له — بابٌ يُرى ولا يُفتح."""
    teacher = person("معلّم", "teacher")

    resp = _get(teacher, "schedule_print")

    assert resp.status_code == 200


def test_the_printed_sheet_is_the_teachers_own(db, person):
    teacher = person("معلّم", "teacher")
    other = person("زميل", "teacher")

    body = _get(teacher, "schedule_print", f"?view=teacher&teacher={other.id}").content.decode()

    assert other.full_name not in body, "لا يطبع جدول زميله ولو طلبه بالرابط"


# ── ولا يتصفّح غيره ──────────────────────────────────────────────────


def test_a_teacher_cannot_read_a_colleagues_schedule(db, person):
    teacher = person("معلّم", "teacher")
    other = person("زميل", "teacher")

    body = _get(teacher, "weekly_schedule", f"?teacher={other.id}").content.decode()

    assert other.full_name not in body


def test_a_teacher_cannot_read_a_whole_class_schedule(db, person, school):
    from core.models import ClassGroup

    teacher = person("معلّم", "teacher")
    cg = ClassGroup.objects.create(
        school=school, grade="G7", section="9", academic_year="2026-2027"
    )

    body = _get(teacher, "weekly_schedule", f"?class={cg.id}").content.decode()

    assert str(cg) not in body


# ── والقيادة على حالها ───────────────────────────────────────────────


@pytest.mark.parametrize("role", sorted(SCHEDULE_BROWSE_ROLES))
def test_the_browsers_still_browse(db, person, role):
    """الإصلاح يضيّق على المعلّم ولا يمسّ من وظيفتُه تصفّح الجداول."""
    browser = person(f"متصفّح {role}", role)
    other = person(f"معلّمٌ آخر {role}", "teacher")

    body = _get(browser, "weekly_schedule", f"?teacher={other.id}").content.decode()

    assert other.full_name in body


# ── الورقة تحمل توقيت الحصص ───────────────────────────────────────────


def test_the_printed_sheet_carries_the_period_times(db, person, school):
    """كانت الخلايا بلا توقيت — والورقة تُعلَّق في غرفة المعلّم."""
    import datetime as dt

    from core.models import ClassGroup
    from operations.models import ScheduleSlot, Subject

    teacher = person("معلّم", "teacher")
    cg = ClassGroup.objects.create(
        school=school, grade="G8", section="9", academic_year="2026-2027"
    )
    subject = Subject.objects.create(school=school, name_ar="الرياضيات")
    ScheduleSlot.objects.create(
        school=school,
        teacher=teacher,
        class_group=cg,
        subject=subject,
        day_of_week=0,
        period_number=1,
        start_time=dt.time(7, 10),
        end_time=dt.time(7, 55),
        academic_year="2026-2027",
    )

    body = _get(teacher, "schedule_print", "?year=2026-2027").content.decode()

    assert "07:10" in body and "07:55" in body


def test_the_times_come_from_the_data_not_the_code():
    """توقيتٌ مكتوبٌ في الشيفرة يصير كذبةً يوم تُغيّر المدرسة جدولها."""
    import pathlib

    src = pathlib.Path("operations/services.py").read_text(encoding="utf-8")
    body = src.split("def period_times", 1)[1].split("@staticmethod", 1)[0]

    assert "TimeSlotConfig" in body, "ما تُعلنه المدرسة أوّلاً"
    assert "ScheduleSlot" in body, "ثمّ ما في الحصص نفسها"
    assert "07:10" not in body and "time(7" not in body


def test_a_teacher_is_not_offered_a_selector_they_cannot_use(db, person):
    teacher = person("معلّم", "teacher")

    body = _get(teacher, "schedule_print").content.decode()

    assert '<form id="schedule-view-form"' not in body
    assert "getElementById('schedule-view-form')" not in body, "ولا سكربتٌ يخدمها"

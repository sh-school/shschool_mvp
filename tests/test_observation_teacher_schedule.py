"""[QUALITY] SOS-20260915: صفُّ جدول المعلّم عند إنشاء الزيارة الصفّية.

جاء في البلاغ: عند اختيار المعلّم والتاريخ يظهر جدولُ ذلك
اليوم، وتُختار الحصّةُ منه بنقرة — لا تُكتب المادّة والشعبة عن ظهر قلب.
والمصدر Session نفسه الذي يقرأه جدولُ المعلّم اليوميّ — لا نسخةٌ ثانية.
"""

import datetime as dt

import pytest
from django.urls import reverse

from operations.models import Session, Subject

pytestmark = pytest.mark.django_db

DAY = dt.date(2026, 9, 20)  # أحد — يوم دراسة


@pytest.fixture
def subject(school):
    return Subject.objects.create(school=school, name_ar="الرياضيات", code="MATH")


@pytest.fixture
def a_session(school, class_group, teacher_user, subject):
    return Session.objects.create(
        school=school,
        class_group=class_group,
        teacher=teacher_user,
        subject=subject,
        date=DAY,
        start_time=dt.time(7, 10),
        end_time=dt.time(7, 55),
        status="scheduled",
    )


def test_no_query_asks_to_choose(client, coordinator_user):
    client.force_login(coordinator_user)

    html = client.get(reverse("observation_teacher_schedule")).content.decode()

    assert "اختر المعلّم والتاريخ" in html


def test_a_session_becomes_a_clickable_period(client, coordinator_user, teacher_user, a_session):
    client.force_login(coordinator_user)

    html = client.get(
        reverse("observation_teacher_schedule"),
        {"teacher": teacher_user.id, "observation_date": DAY.isoformat()},
    ).content.decode()

    assert 'data-period="1"' in html
    assert f'data-class-group="{a_session.class_group_id}"' in html
    assert f'data-subject="{a_session.subject_id}"' in html
    assert "الرياضيات" in html


def test_period_number_comes_from_the_slot_not_the_days_order(
    client, coordinator_user, teacher_user, school, class_group, subject
):
    """معلّمٌ حصّتاه اليوم في ح2 وح4 — لا ح1 وح2 بالعدّ البسيط لترتيبهما في يومه.

    كانت `teacher_schedule_context` تُرقّم بـ`enumerate` على ترتيب حصص المعلّم في
    يومه لا برقم الحصّة الحقيقيّ من `ScheduleSlot` — فيُختار رقمٌ خاطئ بنقرةٍ
    واحدة ويُكتب في محضر الزيارة نفسه.
    """
    from operations.models import ScheduleSlot

    ScheduleSlot.objects.create(
        school=school,
        teacher=teacher_user,
        class_group=class_group,
        subject=subject,
        day_of_week=0,
        period_number=2,
        start_time=dt.time(8, 0),
        end_time=dt.time(8, 45),
    )
    ScheduleSlot.objects.create(
        school=school,
        teacher=teacher_user,
        class_group=class_group,
        subject=subject,
        day_of_week=0,
        period_number=4,
        start_time=dt.time(10, 0),
        end_time=dt.time(10, 45),
    )
    Session.objects.create(
        school=school,
        class_group=class_group,
        teacher=teacher_user,
        subject=subject,
        date=DAY,
        start_time=dt.time(8, 0),
        end_time=dt.time(8, 45),
        status="scheduled",
    )
    Session.objects.create(
        school=school,
        class_group=class_group,
        teacher=teacher_user,
        subject=subject,
        date=DAY,
        start_time=dt.time(10, 0),
        end_time=dt.time(10, 45),
        status="scheduled",
    )

    client.force_login(coordinator_user)
    html = client.get(
        reverse("observation_teacher_schedule"),
        {"teacher": teacher_user.id, "observation_date": DAY.isoformat()},
    ).content.decode()

    assert 'data-period="2"' in html
    assert 'data-period="4"' in html
    assert 'data-period="1"' not in html


def test_no_sessions_falls_back_to_manual_entry(client, coordinator_user, teacher_user):
    client.force_login(coordinator_user)

    html = client.get(
        reverse("observation_teacher_schedule"),
        {"teacher": teacher_user.id, "observation_date": DAY.isoformat()},
    ).content.decode()

    assert "أدخل المادّة والشعبة والحصّة يدويّاً" in html


def test_an_invalid_date_is_reported_not_500(client, coordinator_user, teacher_user):
    client.force_login(coordinator_user)

    resp = client.get(
        reverse("observation_teacher_schedule"),
        {"teacher": teacher_user.id, "observation_date": "ليس-تاريخاً"},
    )

    assert resp.status_code == 200
    assert "تاريخٌ غير صالح" in resp.content.decode()


def test_the_hx_include_selector_matches_the_forms_date_field_name():
    """SOS-20260915 (بلاغ «لم تُحلّ حتى الآن»، 2026-09-17): كان الطلبُ يقرأ
    `?date=` بينما حقلُ التاريخ في الاستمارة اسمُه `observation_date`
    (`name="observation_date"` — اسمُ حقل النموذج الذي يُحفظ في القاعدة،
    لا يُغيَّر لأجل هذه الميزة)، و`hx-include` يرسل الحقولَ بأسمائها كما
    هي — فيصل الخادمَ تاريخاً فارغاً دائماً مهما اختار المستخدم، وصفُّ
    الجدول يبقى عالقاً على «اختر المعلّم والتاريخ» مهما فعل المستخدم.

    هذا الاختبار يقرأ مصدر القالب مباشرةً فيضمن أن الاسم الذي يقرؤه
    `observation_teacher_schedule` (`request.GET.get("observation_date")`)
    هو نفسُه اسمُ حقل `<input>` الفعليّ — لا نسخةً قد تختلف صامتاً.
    """
    import pathlib

    source = pathlib.Path("templates/quality/observation_form.html").read_text(encoding="utf-8")

    assert 'name="observation_date" id="qobs-date"' in source
    assert 'request.GET.get("observation_date")' in pathlib.Path(
        "quality/observation_views.py"
    ).read_text(encoding="utf-8")


def test_editing_a_saved_visit_shows_its_own_day_from_first_load(
    client, school, coordinator_user, teacher_user, a_session
):
    """فتحُ التعديل لا ينتظر تغيير المعلّم أو التاريخ ليعرض صفّ الجدول —
    schedule_row في `_form_context` يُعبَّأ من بيانات الزيارة المحفوظة."""
    from quality.observation_models import ClassroomObservation

    obs = ClassroomObservation.objects.create(
        school=school,
        teacher=teacher_user,
        observer=coordinator_user,
        created_by=coordinator_user,
        observation_date=DAY,
    )
    client.force_login(coordinator_user)

    html = client.get(reverse("observation_edit", args=[obs.id])).content.decode()

    assert f'data-class-group="{a_session.class_group_id}"' in html


FRIDAY = dt.date(2026, 9, 18)
SATURDAY = dt.date(2026, 9, 19)


@pytest.mark.parametrize("weekend_day", [FRIDAY, SATURDAY])
def test_weekend_date_shows_not_a_school_day_not_an_empty_schedule(
    client, coordinator_user, teacher_user, weekend_day
):
    """الجمعة والسبت لا حصصَ فيهما أصلاً — رسالةٌ صريحة بدل صفٍّ فارغٍ صامت
    يُفهم خطأً على أنّه عطلٌ في الميزة."""
    client.force_login(coordinator_user)

    html = client.get(
        reverse("observation_teacher_schedule"),
        {"teacher": teacher_user.id, "observation_date": weekend_day.isoformat()},
    ).content.decode()

    assert "ليس يومَ دراسةٍ" in html


def test_create_form_defaults_to_a_school_day_not_literally_today(client, coordinator_user):
    """قيمةُ حقل التاريخ الافتراضيّة عند الإنشاء يومُ دراسةٍ حقيقيّ — لا اليوم
    حرفيّاً، الذي قد يصادف عطلةً فيُفتح الاستمارةُ على جدولٍ فارغ."""
    from operations.school_days import is_school_day

    client.force_login(coordinator_user)

    html = client.get(reverse("observation_create")).content.decode()

    import re

    m = re.search(r'id="qobs-date"[^>]*value="(\d{4}-\d{2}-\d{2})"', html)
    assert m, "حقلُ التاريخ بلا قيمةٍ افتراضية"
    default = dt.date.fromisoformat(m.group(1))
    assert is_school_day(coordinator_user.get_school(), default)

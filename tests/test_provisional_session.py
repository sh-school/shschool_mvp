"""الرصدُ بحصّةٍ مؤقّتة للمعلّم (W-20261005-006، D-217م وD-218م): خدمةُ الإنشاء ومساراتُها ومفتاحُ التشغيل.

المعلّمُ ينشئ لشُعب إسناده فقط وفي اليوم الدراسيّ الجاري فقط (404 لا 403)، برقمِ حصّةٍ 1–7 وزمنٍ من `TimeSlotConfig`، ومفتاحُ
`PROVISIONAL_SESSIONS_ENABLED` يعزل الميزةَ كلَّها (مطفأً: لا مسارَ ولا زرّ ولا إنشاء). والمؤقّتةُ تُغلق ولا تُحذف.
"""

import datetime as dt
import re

import pytest
from django.db import IntegrityError
from django.urls import reverse
from django.utils import timezone

from core.models import AuditLog
from operations.models import Session, Subject, SubjectClassAssignment
from operations.services import provisional_session as provisional
from tests.attendance_fixtures import *  # noqa: F401,F403
from tests.attendance_fixtures import MONDAY, SATURDAY, SUNDAY, _staff

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


def test_a_teacher_creates_a_provisional_session_for_an_assigned_class(
    school, assigned, teacher, subject
):
    session, created = provisional.create(teacher, school, assigned.id, 1)

    assert created is True
    assert (session.provisional, session.teacher, session.class_group) == (True, teacher, assigned)
    assert (session.date, session.period_number, session.subject) == (SUNDAY, 1, subject)
    # الزمنُ من TimeSlotConfig لجرس الشعبة لا من الرقم
    assert (session.start_time, session.end_time) == (dt.time(7, 10), dt.time(7, 55))
    assert session.provisional_until > timezone.now() + dt.timedelta(days=13)
    assert AuditLog.objects.filter(
        object_id=str(session.pk), object_repr__contains="مؤقّتة"
    ).exists()


def test_creating_twice_returns_the_same_session(school, assigned, teacher):
    first, _ = provisional.create(teacher, school, assigned.id, 2)

    again, created = provisional.create(teacher, school, assigned.id, 2)

    assert (again.pk, created) == (first.pk, False)
    assert Session.objects.filter(provisional=True).count() == 1


def test_a_class_that_is_not_assigned_is_not_found(school, assigned, other_teacher):
    with pytest.raises(provisional.ProvisionalNotAllowedError):
        provisional.create(other_teacher, school, assigned.id, 1)
    assert not Session.objects.filter(provisional=True).exists()


@pytest.mark.parametrize("day", [SUNDAY - dt.timedelta(days=7), MONDAY, SATURDAY, FRIDAY])
def test_only_the_current_school_day_is_allowed(school, assigned, teacher, day):
    with pytest.raises(provisional.ProvisionalNotAllowedError):
        provisional.create(teacher, school, assigned.id, 1, day=day)


@pytest.mark.parametrize("number", [0, 8, -1, "x", None])
def test_a_period_outside_1_to_7_is_refused_in_the_service(school, assigned, teacher, number):
    with pytest.raises(provisional.ProvisionalRefusedError):
        provisional.create(teacher, school, assigned.id, number)


def test_a_period_with_no_bell_time_for_the_class_is_refused(school, assigned, teacher):
    with pytest.raises(provisional.ProvisionalRefusedError):
        provisional.create(teacher, school, assigned.id, 5)  # جرسُ الاختبار ثلاثُ حصصٍ فقط


def test_a_real_session_of_another_teacher_does_not_block_the_provisional_one(
    school, assigned, teacher, other_teacher, session
):
    """واقعةُ المالك (12/2): للشعبة حصّةٌ حقيقيّةٌ مولَّدةٌ من جدول المنصّة لمعلّمٍ **آخر** في الوقت نفسِه — جدولُ المنصّة غيرُ المعتمد قد يخالف الواقع،
    فتُنشأ المؤقّتةُ ويُرصد عليها (D-229م) وتبقى الحقيقيّةُ كما هي لا تُلمس ولا تُغلق المؤقّتة."""
    Session.objects.filter(pk=session.pk).update(teacher=other_teacher)

    made, created = provisional.create(teacher, school, assigned.id, 1)

    assert created is True and made.provisional is True and made.teacher_id == teacher.id
    session.refresh_from_db()
    assert session.teacher_id == other_teacher.id and session.provisional is False
    assert made.provisional_until > timezone.now(), "لا تُغلق بحقيقيّةِ معلّمٍ آخر"


def test_a_real_session_of_the_same_teacher_in_the_slot_is_opened_not_refused(
    school, assigned, teacher, session, client_as
):
    """واقعةُ 8500: المعلّمُ أُسندت إليه حصّةٌ قائمةٌ لهذه الشعبة (ح1) فاختارها — تُفتح لا يظهر «لهذه الشعبة حصّةٌ في هذا الوقت»."""
    opened, created = provisional.create(teacher, school, assigned.id, 1)

    assert (opened.pk, created, opened.provisional) == (session.pk, False, False)
    assert not Session.objects.filter(provisional=True).exists()

    response = client_as(teacher).post(
        reverse("provisional_create", args=[assigned.id]), {"period": "1"}
    )
    assert response.status_code == 302
    assert (
        response.url == f"{reverse('provisional_class', args=[assigned.id])}?session={session.id}"
    )

    choices = provisional.period_choices(teacher, school, assigned)
    assert choices[0].session is not None and choices[0].session.pk == session.pk


def test_the_period_times_are_isolated_left_to_right_so_they_do_not_flip_in_rtl(
    client_as, assigned, teacher
):
    """واقعةُ 8500: «07:10–08:00» ظهرت «08:00–07:10» لأنّ النصَّ العدديَّ داخل فقرةٍ RTL يُعكَس — فيُعزل بـ`<bdi dir="ltr">`."""
    body = client_as(teacher).get(reverse("provisional_class", args=[assigned.id])).content.decode()

    assert '<bdi dir="ltr">07:10–07:55</bdi>' in body


def test_a_teacher_busy_in_another_class_in_the_platform_schedule_may_still_record_provisionally(
    school, year, assigned, teacher, wing
):
    """المنصّةُ تقول إنّه يدرّس شعبةً أخرى 08:00 (جدولٌ غيرُ معتمد) — فلا يمنعه ذلك من رصد هذه الشعبة مؤقّتاً (D-229م)."""
    from tests.conftest import ClassGroupFactory

    other = ClassGroupFactory(school=school, grade="G9", section="z", academic_year=year, wing=wing)
    Session.objects.create(
        school=school,
        class_group=other,
        teacher=teacher,
        date=SUNDAY,
        start_time=dt.time(8, 0),
        end_time=dt.time(8, 45),
        status="scheduled",
    )

    made, created = provisional.create(teacher, school, assigned.id, 2)

    assert created is True and made.provisional is True


def test_the_unique_keys_hold_at_the_database(school, assigned, teacher, subject):
    provisional.create(teacher, school, assigned.id, 1)
    with pytest.raises(IntegrityError):
        Session.objects.create(
            school=school,
            class_group=assigned,
            teacher=_staff(school, "teacher", "معلّم ثانٍ", "29000001099"),
            subject=subject,
            date=SUNDAY,
            start_time=dt.time(9, 0),
            end_time=dt.time(9, 45),
            period_number=1,
            provisional=True,
        )


def test_a_provisional_session_is_closed_not_deleted(school, assigned, teacher):
    session, _ = provisional.create(teacher, school, assigned.id, 1)

    assert provisional.close(session, reason="schedule_approved", by=teacher) is True
    assert provisional.close(session, reason="schedule_approved", by=teacher) is False

    session.refresh_from_db()
    assert session.provisional_until <= timezone.now()
    assert Session.objects.filter(pk=session.pk).exists(), "تبقى تاريخاً"
    assert AuditLog.objects.filter(
        object_id=str(session.pk), object_repr__contains="إغلاق"
    ).exists()


# ── الواجهة: المنتقي فوق قائمة الطلبة، 404 لغير المُسنَد، والمفتاح المطفأ ──


def test_the_class_page_puts_the_period_picker_above_the_students(
    client_as, assigned, teacher, kid
):
    body = client_as(teacher).get(reverse("provisional_class", args=[assigned.id])).content.decode()

    assert all(f"ح{n}" in body for n in range(1, 8))
    assert "07:10" in body and "بلا زمن" in body
    assert body.index("pp-picker") < body.index(kid.full_name), "المنتقي فوق قائمة الطلبة"


def test_picking_a_period_creates_it_and_opens_the_register(client_as, assigned, teacher):
    response = client_as(teacher).post(
        reverse("provisional_create", args=[assigned.id]), {"period": "2"}
    )

    session = Session.objects.get(provisional=True)
    assert response.status_code == 302
    assert (
        response.url == f"{reverse('provisional_class', args=[assigned.id])}?session={session.id}"
    )
    assert session.period_number == 2


def test_an_unassigned_teacher_gets_404_not_403(client_as, assigned, other_teacher):
    client = client_as(other_teacher)

    assert client.get(reverse("provisional_class", args=[assigned.id])).status_code == 404
    assert (
        client.post(reverse("provisional_create", args=[assigned.id]), {"period": "1"}).status_code
        == 404
    )
    assert not Session.objects.filter(provisional=True).exists()


def test_the_supervisor_approves_but_does_not_create(client_as, assigned, holder):
    response = client_as(holder).post(
        reverse("provisional_create", args=[assigned.id]), {"period": "1"}
    )

    assert response.status_code == 404
    assert not Session.objects.filter(provisional=True).exists()


def test_a_period_out_of_range_is_refused_with_a_message_not_an_error(client_as, assigned, teacher):
    response = client_as(teacher).post(
        reverse("provisional_create", args=[assigned.id]), {"period": "9"}
    )

    assert response.status_code == 302
    assert response.url == reverse("provisional_class", args=[assigned.id])
    assert not Session.objects.filter(provisional=True).exists()


def test_with_the_switch_off_nothing_exists(client_as, settings, assigned, teacher):
    settings.PROVISIONAL_SESSIONS_ENABLED = False
    client = client_as(teacher)

    assert client.get(reverse("provisional_classes")).status_code == 404
    assert client.get(reverse("provisional_class", args=[assigned.id])).status_code == 404
    assert (
        client.post(reverse("provisional_create", args=[assigned.id]), {"period": "1"}).status_code
        == 404
    )
    assert provisional.assigned_classes(teacher, assigned.school) == []
    assert not Session.objects.filter(provisional=True).exists()
    page = client.get(reverse("teacher_schedule")).content.decode()
    assert "شُعبي للرصد" not in page, "لا زرَّ مطفأً"


def test_with_the_switch_on_the_schedule_offers_the_door(client_as, assigned, teacher):
    page = client_as(teacher).get(reverse("teacher_schedule")).content.decode()

    assert "شُعبي للرصد" in page


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
}


def test_nothing_on_the_schedule_or_register_path_reads_the_switch():
    from pathlib import Path

    root = Path(__file__).resolve().parent.parent
    readers = set()
    for path in root.rglob("*.py"):
        parts = path.relative_to(root).parts
        if (
            parts[0] in {"tests", ".claude", ".venv", "node_modules", "migrations"}
            or "migrations" in parts
        ):
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        if "PROVISIONAL_SESSIONS_ENABLED" in text or "provisional_session" in text:
            readers.add(path.relative_to(root).as_posix())
    assert readers <= KEY_READERS, f"وحدةٌ جديدةٌ تقرأ المفتاح: {sorted(readers - KEY_READERS)}"
    for untouched in (
        "operations/services/schedule_sessions.py",
        "operations/services/swap.py",
        "operations/services/compensatory.py",
        "operations/services/schedule_read.py",
    ):
        assert untouched not in readers


def test_with_the_switch_off_the_session_admin_is_unchanged(settings, rf):
    from django.contrib import admin

    from operations.admin import SessionAdmin

    settings.PROVISIONAL_SESSIONS_ENABLED = False
    model_admin = SessionAdmin(Session, admin.site)
    request = rf.get("/")

    assert "provisional" not in model_admin.get_list_display(request)
    assert "provisional" not in model_admin.get_list_filter(request)
    settings.PROVISIONAL_SESSIONS_ENABLED = True
    assert "provisional" in model_admin.get_list_display(request)


def test_with_the_switch_off_a_real_week_generates_exactly_as_before(
    settings, school, year, klass, teacher, subject, band, bells, monkeypatch
):
    """التوليدُ لا يعرف المفتاح: العددُ نفسُه مطفأً ومشغَّلاً — ولا صفَّ مؤقّتاً يُنشأ من التوليد."""
    from operations.models import ScheduleSlot
    from operations.services import ScheduleService

    ScheduleSlot.objects.create(
        school=school,
        teacher=teacher,
        class_group=klass,
        subject=subject,
        day_of_week=0,
        period_number=1,
        start_time=dt.time(7, 10),
        end_time=dt.time(7, 55),
        academic_year=year,
    )
    counts = {}
    for flag in (False, True):
        settings.PROVISIONAL_SESSIONS_ENABLED = flag
        Session.objects.all().delete()
        counts[flag] = ScheduleService.ensure_sessions_for_date(school, SUNDAY)
        assert not Session.objects.filter(provisional=True).exists()
    assert counts[False] == counts[True]


# ── جدولُ «حصصي اليوم» مُعطَّلٌ بمفتاح الحصّة المؤقّتة (أمرُ المالك، W-20261005-006) ──


def _schedule_page(client, user):
    return client.get(reverse("teacher_schedule")).content.decode()


def _anchors_to(page, *names):
    """كلُّ وسوم <a> في الصفحة إلى هذه المسارات (بأسمائها) — لمعرفة هل عطّلها `inert`."""
    urls = [reverse(n) for n in names]
    return [tag for tag in re.findall(r"<a [^>]*>", page) if any(f'href="{u}' in tag for u in urls)]


def test_with_the_switch_on_the_teachers_schedule_is_switched_off_everywhere(
    client_as, assigned, teacher, session
):
    page = _schedule_page(client_as(teacher), teacher)

    # الجدولُ: لا رابطَ حضورٍ فعّال، وتحته «تحت الإجراء» حرفاً (D-228م)
    assert f'href="{reverse("attendance", args=[session.id])}"' not in page
    assert 'aria-disabled="true"' in page and "sessions-table is-off" in page
    assert '<p class="ui-note sessions-off-note">تحت الإجراء</p>' in page
    assert "الجدولُ غيرُ معتمدٍ بعدُ" not in page
    # مفاتيحُ الترويسة مطفأةٌ: لا رابطَ تبديلٍ ولا تعويض في الترويسة، والترشيحُ بالتاريخ معطَّل
    assert '<span class="btn-secondary btn-sm prov-off"' in page
    assert re.search(r'<form class="schedule-date prov-off" inert', page)
    # ومفاتيحُ القائمة (التبديل والتعويض والجدول) معطَّلةٌ بـinert حيث وُجدت
    nav = _anchors_to(page, "swap_list", "compensatory_list") + [
        tag
        for tag in _anchors_to(page, "teacher_schedule")
        if "class=" in tag  # لا فتاتُ الخبز
    ]
    assert nav and all("inert" in tag and "data-prov-off" in tag for tag in nav), nav
    # «جدولي» (الجدولُ الأسبوعيّ للمعلّم) فعّالٌ يفتح (D-231م)، وبقيّةُ بنود القائمة مقفلة
    weekly = [
        tag
        for tag in re.findall(r"<a [^>]*>", page)
        if f'href="{reverse("weekly_schedule")}?view=teacher' in tag
    ]
    assert weekly and all(
        "inert" not in tag and "data-prov-off" not in tag for tag in weekly
    ), weekly
    # بابُ الرصد المؤقّت وحدَه يعمل
    assert f'href="{reverse("provisional_classes")}"' in page


def test_with_the_switch_off_the_schedule_is_exactly_as_it_was(
    client_as, settings, assigned, teacher, session
):
    settings.PROVISIONAL_SESSIONS_ENABLED = False

    page = _schedule_page(client_as(teacher), teacher)

    assert f'href="{reverse("attendance", args=[session.id])}"' in page
    assert "is-off" not in page and "sessions-off-note" not in page
    assert "data-prov-off" not in page and "prov-off" not in page and "تحت الإجراء" not in page
    assert 'aria-disabled="true"' not in page.split('class="sessions-table')[1].split("</table>")[0]


def test_leadership_view_of_the_schedule_is_untouched_by_the_switch(
    client_as, assigned, session, principal_user
):
    page = client_as(principal_user).get(reverse("teacher_schedule")).content.decode()

    assert "sessions-off-note" not in page and "is-off" not in page


# ── الصفحةُ الرئيسيّةُ للمعلّم (D-227م): تُخفى حصصُه من جدول المنصّة وتحلّ بطاقةُ «رصدُ الغياب (مؤقّت)» ──


def test_with_the_switch_on_the_home_hides_the_platform_sessions_and_offers_the_temporary_card(
    client_as, assigned, teacher, session
):
    page = client_as(teacher).get(reverse("dashboard")).content.decode()

    assert f'href="{reverse("attendance", args=[session.id])}"' not in page, "لا حصصَ من جدول المنصّة"
    assert "رصدُ الغياب (مؤقّت — إلى حين اعتماد جدول المنصّة)" in page
    assert f'href="{reverse("provisional_classes")}"' in page
    # بلاطاتُ الجدول والتبديل مطفأةٌ بلا رابط (مظهرُ البلاطة نفسُه بلا href)
    for tile_text in (
        "حصصي هذا الأسبوع",
        "جداولُ كلّ المعلّمين",
        "تبديلُ حصّةٍ مع زميل",
        "حصصُ اليوم — والحضورُ",
    ):
        assert tile_text not in page, f"بلاطةُ الجدول مخفيّةٌ لا مُعطَّلة: {tile_text}"
    assert "action-card prov-off" not in page


def test_with_the_switch_off_the_home_is_exactly_as_it_was(
    client_as, settings, assigned, teacher, session
):
    settings.PROVISIONAL_SESSIONS_ENABLED = False

    page = client_as(teacher).get(reverse("dashboard")).content.decode()

    assert f'href="{reverse("attendance", args=[session.id])}"' in page
    assert "رصدُ الغياب (مؤقّت" not in page and "prov-off" not in page


# ── صفحةُ الشعبة بشبكة الكشف نفسِها (D-229م، D-16 layout-sheet) ──


def test_before_choosing_a_period_the_grid_is_shown_disabled_with_the_prompt(
    client_as, assigned, teacher, kid
):
    body = client_as(teacher).get(reverse("provisional_class", args=[assigned.id])).content.decode()

    assert "اختر الحصّة أوّلاً" in body
    assert 'class="auto-grid prov-off"' in body and kid.full_name in body
    assert "rec-form" not in body, "لا نموذجَ رصدٍ قبل الاختيار"
    assert "layout-sheet" in body


def test_after_choosing_the_shared_register_sheet_is_in_the_same_page(
    client_as, assigned, teacher, kid
):
    client = client_as(teacher)
    response = client.post(reverse("provisional_create", args=[assigned.id]), {"period": "2"})

    body = client.get(response.url).content.decode()

    assert (
        "rec-form" in body and kid.full_name in body
    ), "شبكةُ كشف الحصّة (بطاقةُ كلّ طالب) في الصفحة نفسِها"
    assert "اختر الحصّة أوّلاً" not in body
    assert (
        reverse("attendance_period_entries", args=[Session.objects.get(provisional=True).id])
        in body
    )


def test_a_session_param_of_another_teacher_or_class_shows_no_sheet(
    client_as, assigned, teacher, other_teacher, school, klass, subject, kid
):
    theirs = Session.objects.create(
        school=school,
        class_group=klass,
        teacher=other_teacher,
        subject=subject,
        date=SUNDAY,
        start_time=dt.time(8, 0),
        end_time=dt.time(8, 45),
        status="scheduled",
    )

    body = (
        client_as(teacher)
        .get(f"{reverse('provisional_class', args=[assigned.id])}?session={theirs.id}")
        .content.decode()
    )

    assert "rec-form" not in body and "اختر الحصّة أوّلاً" in body


# ── الجدولُ الأسبوعيّ للمعلّم: يُفتح مُطفأً كلُّ شيءٍ فيه و«تحت الإجراء» (D-231م) ──


def test_with_the_switch_on_the_teacher_opens_the_weekly_schedule_switched_off(
    client_as, assigned, teacher
):
    url = f"{reverse('weekly_schedule')}?view=teacher&teacher={teacher.id}"

    response = client_as(teacher).get(url)
    page = response.content.decode()

    assert response.status_code == 200, "«جدولي» يفتح"
    assert '<p class="ui-note sessions-off-note">تحت الإجراء</p>' in page
    # مفاتيحُ الترويسة والتصدير مُعطَّلةٌ بـinert، والجدولُ خافت
    assert re.search(r'<div class="schedule-head prov-off" inert', page)
    assert re.search(r'<div class="table-wrap prov-off"', page)


def test_with_the_switch_off_the_weekly_schedule_is_as_it_was(
    client_as, settings, assigned, teacher
):
    settings.PROVISIONAL_SESSIONS_ENABLED = False

    page = (
        client_as(teacher)
        .get(f"{reverse('weekly_schedule')}?view=teacher&teacher={teacher.id}")
        .content.decode()
    )

    assert "prov-off" not in page and "تحت الإجراء" not in page


def test_the_under_action_note_is_centered_triple_size_and_glowing_red():
    """أمرُ المالك: «تحت الإجراء» وسطَ السطر وأكبرَ 300% وبالأحمر المتوهّج."""
    from tests.css_source import read_css

    css = read_css()
    rule = css[css.index(".sessions-off-note {") :].split("}", 1)[0]

    assert "text-align: center" in rule
    assert "calc(var(--text-sm) * 3)" in rule
    assert "var(--status-danger)" in rule and "text-shadow" in rule

"""الانتقال الداخلي بين شعب المدرسة (W-20261005-008، المرحلة 2؛ D-201م: النقلُ يرحّل معه كلّ شيء).

الإتمامُ ذرّيّ: يُغلق التسجيلَ القديم وينشئ الجديد بتاريخ الانتقال بلا حذف. ويُرفض هدفٌ من صفٍّ آخر أو شعبةُ الطالب نفسُها،
وتاريخٌ في المستقبل. والوارد والصادر الخارجيّ كما كانا.
"""

import datetime as dt

import pytest
from django.urls import reverse

from core.models import StudentEnrollment
from student_affairs.internal_transfer import internal_target_error
from student_affairs.models import StudentTransfer
from tests.attendance_fixtures import *  # noqa: F401,F403
from tests.transfer_chain_support import run_full_chain
from tests.visual_snapshots import FIXED_NOW

# الساعةُ مثبَّتةٌ: نافذةُ رجوع التاريخ تقرأ «اليوم»، فيُحسب الماضي من اليوم المثبَّت (W-20261008-021).
pytestmark = [pytest.mark.django_db, pytest.mark.pin_clock]

PAST = FIXED_NOW.date() - dt.timedelta(days=1)  # النقلُ بتاريخٍ ماضٍ محدودٌ بأسبوع


@pytest.fixture
def klass2(school, year, wing):
    return ClassGroupFactory(
        school=school, grade="G7", section="2", level_type="prep", academic_year=year, wing=wing
    )


@pytest.fixture
def other_grade(school, year, wing):
    return ClassGroupFactory(
        school=school, grade="G8", section="1", level_type="prep", academic_year=year, wing=wing
    )


def _request(school, student, target, user, date=PAST, status="approved"):
    return StudentTransfer.objects.create(
        school=school,
        student=student,
        direction="internal",
        other_school_name=school.name,
        to_class_group=target,
        transfer_date=date,
        status=status,
        academic_year="2026-2027",
        created_by=user,
        updated_by=user,
    )


def _complete(client, user, transfer):
    client.force_login(user)
    return client.post(
        reverse("student_affairs:transfer_review", args=[transfer.pk]),
        {"action": "completed", "notes": ""},
    )


def test_completing_moves_the_enrollment_without_deleting_anything(
    client, principal_user, student_affairs_coordinator_user, school, kid, klass, klass2
):
    transfer = _request(school, kid, klass2, student_affairs_coordinator_user)

    _complete(client, principal_user, transfer)

    transfer.refresh_from_db()
    assert transfer.status == "completed"
    old = StudentEnrollment.objects.get(student=kid, class_group=klass)
    new = StudentEnrollment.objects.get(student=kid, class_group=klass2)
    assert (old.is_active, new.is_active, new.enrolled_at) == (False, True, PAST)
    assert StudentEnrollment.objects.filter(student=kid).count() == 2


def test_the_move_does_not_touch_the_membership(
    client, principal_user, student_affairs_coordinator_user, school, kid, klass2
):
    transfer = _request(school, kid, klass2, student_affairs_coordinator_user)

    _complete(client, principal_user, transfer)

    assert kid.memberships.filter(school=school, is_active=True).exists()


@pytest.mark.parametrize("target_fixture", ["other_grade", "klass"])
def test_a_target_of_another_grade_or_the_same_class_is_refused_and_nothing_is_written(
    client,
    principal_user,
    student_affairs_coordinator_user,
    school,
    kid,
    klass,
    request,
    target_fixture,
):
    target = request.getfixturevalue(target_fixture)
    transfer = _request(school, kid, target, student_affairs_coordinator_user)

    _complete(client, principal_user, transfer)

    transfer.refresh_from_db()
    assert transfer.status == "approved"
    assert list(StudentEnrollment.objects.filter(student=kid)) == [
        StudentEnrollment.objects.get(student=kid, class_group=klass)
    ]
    assert StudentEnrollment.objects.get(student=kid).is_active


def test_a_future_date_is_refused(
    client, principal_user, student_affairs_coordinator_user, school, kid, klass2
):
    transfer = _request(
        school, kid, klass2, student_affairs_coordinator_user, date=dt.date(2099, 1, 1)
    )

    _complete(client, principal_user, transfer)

    transfer.refresh_from_db()
    assert transfer.status == "approved"
    assert StudentEnrollment.objects.filter(student=kid).count() == 1


def test_a_date_older_than_the_backdate_window_is_refused_and_a_recent_one_passes(
    school, kid, klass2, student_affairs_coordinator_user
):
    """نقلٌ بتاريخٍ ماضٍ يعيد قراءةَ أيّامٍ رُصدت فعلاً، فيُحدّ بأسبوع (W-20261004-027 — سياسةٌ للمالك)."""
    today = FIXED_NOW.date()
    old = _request(
        school, kid, klass2, student_affairs_coordinator_user, date=today - dt.timedelta(days=30)
    )
    recent = _request(
        school, kid, klass2, student_affairs_coordinator_user, date=today - dt.timedelta(days=3)
    )

    assert "أقدمُ" in internal_target_error(old)
    assert internal_target_error(recent) == ""


def test_a_move_between_a_regular_and_a_special_education_section_is_refused(
    school, kid, klass, special_klass, student_affairs_coordinator_user
):
    """عتباتُ الغياب تتبع شعبةَ الطالب؛ فالعبورُ بين العاديّة والتربية الخاصّة يُمنع حتى يحسم المالكُ أثرَه."""
    into = _request(school, kid, special_klass, student_affairs_coordinator_user)

    assert "تربيةٍ خاصّةٍ" in internal_target_error(into)


def test_a_student_without_an_active_enrollment_cannot_move(
    school, student_user, klass2, student_affairs_coordinator_user
):
    transfer = _request(school, student_user, klass2, student_affairs_coordinator_user)

    assert "بلا تسجيل" in internal_target_error(transfer)


def test_the_create_form_requires_a_target_for_an_internal_move(
    client, student_affairs_coordinator_user, kid
):
    client.force_login(student_affairs_coordinator_user)

    response = client.post(
        reverse("student_affairs:transfer_create"),
        {"student_id": str(kid.pk), "direction": "internal", "transfer_date": PAST.isoformat()},
    )

    assert response.status_code == 200
    assert not StudentTransfer.objects.exists()


def test_the_create_form_saves_an_internal_request_and_shows_the_class_beside_the_student(
    client, student_affairs_coordinator_user, school, kid, klass, klass2
):
    client.force_login(student_affairs_coordinator_user)

    # صفُّ الطالب وشعبته يصلان مع المقترَح من البحث بالاسم (W-20261114-010)
    page = client.get(reverse("student_affairs:transfer_student_search"), {"q": "طالب"})
    assert f'data-class-id="{klass.pk}"' in page.content.decode()
    assert klass.short_label in page.content.decode()

    response = client.post(
        reverse("student_affairs:transfer_create"),
        {
            "student_id": str(kid.pk),
            "direction": "internal",
            "to_class_group_id": str(klass2.pk),
            "transfer_date": PAST.isoformat(),
        },
    )

    assert response.status_code == 302
    saved = StudentTransfer.objects.get()
    assert (saved.direction, saved.to_class_group_id) == ("internal", klass2.pk)


def test_the_create_form_refuses_a_target_of_another_grade(
    client, student_affairs_coordinator_user, kid, other_grade
):
    client.force_login(student_affairs_coordinator_user)

    response = client.post(
        reverse("student_affairs:transfer_create"),
        {
            "student_id": str(kid.pk),
            "direction": "internal",
            "to_class_group_id": str(other_grade.pk),
            "transfer_date": PAST.isoformat(),
        },
    )

    assert response.status_code == 200
    assert not StudentTransfer.objects.exists()


def test_an_external_outgoing_transfer_still_deactivates_as_before(
    client, student_affairs_coordinator_user, school, kid, klass
):
    transfer = StudentTransfer.objects.create(
        school=school,
        student=kid,
        direction="out",
        other_school_name="مدرسة أخرى",
        transfer_date=PAST,
        academic_year="2026-2027",
        created_by=student_affairs_coordinator_user,
        updated_by=student_affairs_coordinator_user,
    )

    run_full_chain(transfer, student_affairs_coordinator_user)

    assert not StudentEnrollment.objects.get(student=kid, class_group=klass).is_active


# ── بحثُ الطالب combobox ورسالةُ منع الإرسال بلا اختيار (W-20261123-013) ──


def test_student_search_results_are_listbox_options_with_class_chip(
    client, student_affairs_coordinator_user, kid, klass
):
    client.force_login(student_affairs_coordinator_user)

    body = client.get(
        reverse("student_affairs:transfer_student_search"), {"q": "طالب"}
    ).content.decode()

    assert 'role="option"' in body and 'id="transfer-student-opt-0"' in body
    assert "sa-combo__chip" in body and klass.short_label in body
    assert "<button" not in body


def test_create_form_renders_an_aria_combobox_with_a_listbox_and_status_line(
    client, student_affairs_coordinator_user
):
    client.force_login(student_affairs_coordinator_user)

    body = client.get(reverse("student_affairs:transfer_create")).content.decode()

    assert 'role="combobox"' in body and 'aria-autocomplete="list"' in body
    assert 'aria-controls="transfer-student-results"' in body
    assert 'role="listbox"' in body and "data-student-clear" in body
    assert 'aria-live="polite"' in body and "data-student-error" in body


def test_post_without_a_student_shows_the_arabic_choose_student_message(
    client, student_affairs_coordinator_user, klass2
):
    client.force_login(student_affairs_coordinator_user)

    response = client.post(
        reverse("student_affairs:transfer_create"),
        {
            "direction": "internal",
            "to_class_group_id": str(klass2.pk),
            "transfer_date": PAST.isoformat(),
        },
    )

    body = response.content.decode()
    assert response.status_code == 200
    assert body.count("يرجى اختيار الطالب.") >= 2  # رسالةُ الخادم + رسالةُ الواجهة المخفيّة
    assert "This field is required" not in body
    assert not StudentTransfer.objects.exists()


def test_post_with_a_malformed_student_id_uses_the_same_arabic_message(
    client, student_affairs_coordinator_user
):
    client.force_login(student_affairs_coordinator_user)

    response = client.post(
        reverse("student_affairs:transfer_create"),
        {
            "student_id": "not-an-id",
            "direction": "in",
            "other_school_name": "مدرسة",
            "transfer_date": PAST.isoformat(),
        },
    )

    body = response.content.decode()
    assert "Enter a valid value" not in body
    assert 'role="alert">يرجى اختيار الطالب.' in body


# ── ملخّص الاتجاه ومراجعة النقل المباشر وتحقّقٌ موحَّد (W-20261124-001) ──


def _direct_data(kid, target, **extra):
    return {
        "student_id": str(kid.pk),
        "direction": "internal",
        "to_class_group_id": str(target.pk),
        "transfer_date": PAST.isoformat(),
        "direct": "1",
        **extra,
    }


def test_create_form_explains_directions_defaults_today_and_counts_the_reason(
    client, principal_user
):
    client.force_login(principal_user)

    body = client.get(reverse("student_affairs:transfer_create")).content.decode()

    assert FIXED_NOW.date().isoformat() in body, "التاريخ الافتراضي اليوم"
    assert "وارد:" in body and "صادر:" in body and "داخلي:" in body
    assert "للمدير والنائب الإداري وحدهما" in body
    assert "data-transfer-summary" in body and "data-reason-count" in body
    assert "الشعبة الحالية" in body


def test_the_first_direct_post_shows_a_review_page_and_writes_nothing(
    client, principal_user, kid, klass, klass2
):
    client.force_login(principal_user)

    response = client.post(reverse("student_affairs:transfer_create"), _direct_data(kid, klass2))

    body = response.content.decode()
    assert response.status_code == 200
    assert "تأكيد النقل" in body and "رجوع للتعديل" in body
    assert klass.short_label in body and klass2.short_label in body and kid.full_name in body
    assert f'name="to_class_group_id" value="{klass2.pk}"' in body
    assert not StudentTransfer.objects.exists()
    assert StudentEnrollment.objects.get(student=kid, is_active=True).class_group == klass


def test_confirming_executes_the_direct_move_from_the_server(client, principal_user, kid, klass2):
    client.force_login(principal_user)

    response = client.post(
        reverse("student_affairs:transfer_create"),
        _direct_data(kid, klass2, confirm_direct="1"),
    )

    assert response.status_code == 302
    assert StudentTransfer.objects.get().status == "completed"
    assert StudentEnrollment.objects.get(student=kid, is_active=True).class_group == klass2


def test_a_coordinator_is_refused_on_both_direct_requests(
    client, student_affairs_coordinator_user, kid, klass2
):
    client.force_login(student_affairs_coordinator_user)
    url = reverse("student_affairs:transfer_create")

    first = client.post(url, _direct_data(kid, klass2))
    second = client.post(url, _direct_data(kid, klass2, confirm_direct="1"))

    assert (first.status_code, second.status_code) == (403, 403)
    assert not StudentTransfer.objects.exists()


def test_back_to_edit_keeps_the_inputs_and_does_not_execute(client, principal_user, kid, klass2):
    client.force_login(principal_user)

    response = client.post(
        reverse("student_affairs:transfer_create"),
        _direct_data(kid, klass2, reason="سبب تجريبي", edit="1"),
    )

    body = response.content.decode()
    assert response.status_code == 200 and "data-transfer-form" in body
    assert PAST.isoformat() in body and "سبب تجريبي" in body
    assert f'value="{kid.pk}"' in body
    assert not StudentTransfer.objects.exists()


def test_an_outgoing_transfer_requires_a_reason_with_a_unified_arabic_message(
    client, student_affairs_coordinator_user, kid
):
    client.force_login(student_affairs_coordinator_user)
    url = reverse("student_affairs:transfer_create")
    data = {
        "student_id": str(kid.pk),
        "direction": "out",
        "other_school_name": "مدرسة أخرى",
        "transfer_date": PAST.isoformat(),
    }

    refused = client.post(url, data)
    accepted = client.post(url, {**data, "reason": "انتقال الأسرة"})

    assert "سبب الانتقال مطلوب في الانتقال الصادر." in refused.content.decode()
    assert accepted.status_code == 302 and StudentTransfer.objects.count() == 1


def test_field_errors_are_arabic_for_date_school_and_class(
    client, student_affairs_coordinator_user, kid
):
    client.force_login(student_affairs_coordinator_user)
    url = reverse("student_affairs:transfer_create")
    base = {"student_id": str(kid.pk), "transfer_date": PAST.isoformat()}

    bad_date = client.post(
        url, {**base, "direction": "in", "other_school_name": "م", "transfer_date": "x"}
    ).content.decode()
    no_school = client.post(url, {**base, "direction": "in"}).content.decode()
    no_class = client.post(url, {**base, "direction": "internal"}).content.decode()

    assert "أدخل تاريخًا صحيحًا." in bad_date and "Enter a valid date" not in bad_date
    assert "اسم المدرسة الأخرى مطلوب." in no_school
    assert "اختر الشعبة المنقول إليها." in no_class

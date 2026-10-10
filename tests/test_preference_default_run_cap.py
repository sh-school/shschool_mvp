"""[SCHEDULE] فخُّ التفضيلات: الافتراضُ لا يُرخي HC5 بصمت (W-20261003-037).

كان `max_consecutive` افتراضُه ٣، فيُنشئ `get_or_create` عند أوّل فتحٍ للشاشة سقفاً شخصيّاً يتقدّم على العامّ.
صار الافتراضُ `NULL` = العامّ، وما فوق العامّ يُقبل بتنبيهٍ ظاهرٍ وسجلّ تدقيق.
"""

import pytest
from django.urls import reverse

from core.models import AuditLog
from operations import scheduler
from operations.models import Subject, SubjectClassAssignment, TeacherPreference
from operations.preference_capacity import (
    daily_capacity,
    effective_run_cap,
    exceeds_general_run_cap,
    weekly_capacity,
)
from operations.scheduler_constraints import MAX_CONSECUTIVE
from tests.conftest import ClassGroupFactory, MembershipFactory, RoleFactory, UserFactory

pytestmark = pytest.mark.django_db
YEAR = "2026-2027"
URL = reverse("teacher_preferences") + f"?year={YEAR}"


@pytest.fixture
def teacher(school):
    user = UserFactory(full_name="معلّمُ الرياضيات")
    MembershipFactory(user=user, school=school, role=RoleFactory(school=school, name="teacher"))
    maths = Subject.objects.create(school=school, name_ar="الرياضيات", code="MAT")
    group = ClassGroupFactory(school=school, grade="G10", level_type="sec", academic_year=YEAR)
    SubjectClassAssignment.objects.create(
        school=school,
        academic_year=YEAR,
        teacher=user,
        class_group=group,
        subject=maths,
        weekly_periods=4,
        is_active=True,
    )
    return user


@pytest.fixture
def superuser(developer_user):
    developer_user.is_staff = developer_user.is_superuser = True
    developer_user.must_change_password = False
    developer_user.save()
    return developer_user


def save(client, teacher, **over):
    client.force_login(teacher)
    payload = {"max_daily_periods": "5", "max_consecutive": "", "max_gap": "", "free_day": ""}
    payload.update(over)
    return client.post(URL, payload, follow=True)


def test_the_model_default_is_null_not_three():
    assert TeacherPreference._meta.get_field("max_consecutive").default is None
    assert TeacherPreference._meta.get_field("max_consecutive").null is True


def test_opening_the_screen_creates_no_personal_cap(client, school, teacher):
    client.force_login(teacher)

    client.get(URL)

    pref = TeacherPreference.objects.get(teacher=teacher, academic_year=YEAR)
    assert pref.max_consecutive is None


def test_saving_with_the_default_keeps_the_general_cap_in_the_generator(client, school, teacher):
    """معلّمٌ حفظ تفضيلاته بالافتراض: لا سقفَ شخصيَّ يصل المولّد فيبقى العامُّ ساريّاً."""
    save(client, teacher)

    assert TeacherPreference.objects.get(teacher=teacher).max_consecutive is None
    tasks = scheduler.build_tasks(school, YEAR)
    assert {m.teacher_id: t.consecutive_cap for t in tasks for m in t.members} == {
        str(teacher.id): 0
    }, "الصفرُ يعني العامّ في المهمّة"


def test_a_personal_cap_above_the_general_is_saved_with_a_visible_warning_and_an_audit(
    client, school, teacher
):
    response = save(client, teacher, max_consecutive="3")

    pref = TeacherPreference.objects.get(teacher=teacher)
    assert pref.max_consecutive == 3, "قبولٌ لا رفض"
    body = response.content.decode()
    assert "أعلى من السقف العامّ" in body and "تم حفظ تفضيلاتك" in body
    entry = AuditLog.objects.get(changes__event="teacher_run_cap_above_general")
    assert entry.changes["value"] == 3 and entry.changes["general"] == MAX_CONSECUTIVE
    assert entry.changes["channel"] == "teacher_preferences"
    assert entry.object_id == str(pref.pk)
    assert "معلّمُ الرياضيات" not in str(entry.changes) + entry.object_repr, "لا اسمَ في الأثر"


def test_the_page_shows_a_persistent_warning_for_a_cap_above_the_general(client, school, teacher):
    save(client, teacher, max_consecutive="3")

    body = client.get(URL).content.decode()

    assert "سقفُك الشخصي (3) أعلى من السقف العام" in body


def test_a_cap_equal_to_the_general_warns_nothing(client, school, teacher):
    response = save(client, teacher, max_consecutive=str(MAX_CONSECUTIVE))

    assert "أعلى من السقف العامّ" not in response.content.decode()
    assert not AuditLog.objects.filter(changes__event="teacher_run_cap_above_general").exists()


def test_leaving_the_field_blank_again_returns_to_the_general(client, school, teacher):
    save(client, teacher, max_consecutive="3")
    save(client, teacher, max_consecutive="")

    assert TeacherPreference.objects.get(teacher=teacher).max_consecutive is None


def test_the_screen_offers_the_general_cap_as_the_default_option(client, school, teacher):
    client.force_login(teacher)

    body = client.get(URL).content.decode()

    assert "السقف العام للمدرسة" in body and "(الافتراضي)" in body
    assert "3 حصص (الافتراضي)" not in body


def test_the_admin_save_of_a_cap_above_the_general_warns_and_audits(
    client, superuser, school, teacher
):
    client.force_login(superuser)
    pref = TeacherPreference.objects.create(teacher=teacher, school=school, academic_year=YEAR)
    url = reverse("admin:operations_teacherpreference_change", args=[pref.pk])
    data = {
        "teacher": teacher.pk,
        "school": school.pk,
        "academic_year": YEAR,
        "max_daily_periods": 5,
        "max_consecutive": 3,
        "notes": "",
    }

    response = client.post(url, data, follow=True)

    assert response.status_code == 200
    pref.refresh_from_db()
    assert pref.max_consecutive == 3
    entry = AuditLog.objects.get(changes__event="teacher_run_cap_above_general")
    assert entry.changes["channel"] == "admin"


def test_none_means_the_general_cap_in_the_capacity_helpers():
    assert effective_run_cap(None) == MAX_CONSECUTIVE and effective_run_cap(3) == 3
    assert exceeds_general_run_cap(None) is False
    assert exceeds_general_run_cap(MAX_CONSECUTIVE) is False
    assert exceeds_general_run_cap(MAX_CONSECUTIVE + 1) is True
    # فراغ ١: بلا سقفٍ شخصيٍّ يلزم نمطُ التباعد (١·٣·٥·٧)، لا كتلٌ بطول ثلاث
    assert daily_capacity(7, None, 1) == daily_capacity(7, MAX_CONSECUTIVE, 1) == 4
    assert daily_capacity(7, 3, 1) > daily_capacity(7, None, 1)
    assert weekly_capacity(5, None, 0) == weekly_capacity(5, MAX_CONSECUTIVE, 0)


def test_the_feasibility_report_and_the_exemption_grid_accept_none(school, teacher):
    from operations import schedule_feasibility as sf
    from operations.exemption_grid import build_grid

    TeacherPreference.objects.create(
        teacher=teacher, school=school, academic_year=YEAR, max_daily_periods=5, max_gap=0
    )

    assert sf.check(school, YEAR) is not None
    grid = build_grid(school, teacher, YEAR)
    assert grid.capacity == weekly_capacity(5, None, 0)

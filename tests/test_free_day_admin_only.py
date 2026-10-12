"""[SCHEDULE] يومُ التفريغ قرارٌ إداريّ لا تفضيلٌ يكتبه المعلّم (W-20261010-025).

كانت شاشةُ المعلّم تُحرّر `free_day` مع أنّه يُغيّر السعةَ الأسبوعيّةَ ويُنقل إلى التوليد قيداً مرجَّحاً بقوّة،
فصار المعلّمُ يقرّر يومَ غيابه من الجدول. الآن يقرؤه المعلّمُ ولا يكتبه، والإدارةُ تكتبه من الأدمن بأثرٍ مدقَّق.
"""

import pytest
from django.urls import reverse

from core.models import AuditLog
from operations import scheduler
from operations.models import Subject, SubjectClassAssignment, TeacherPreference
from tests.conftest import ClassGroupFactory, MembershipFactory, RoleFactory, UserFactory

pytestmark = pytest.mark.django_db
YEAR = "2026-2027"
URL = reverse("teacher_preferences") + f"?year={YEAR}"
WEDNESDAY = 2


@pytest.fixture
def teacher(school):
    user = UserFactory(full_name="معلّمُ العلوم")
    MembershipFactory(user=user, school=school, role=RoleFactory(school=school, name="teacher"))
    subject = Subject.objects.create(school=school, name_ar="العلوم", code="SCI")
    group = ClassGroupFactory(school=school, grade="G10", level_type="sec", academic_year=YEAR)
    SubjectClassAssignment.objects.create(
        school=school,
        academic_year=YEAR,
        teacher=user,
        class_group=group,
        subject=subject,
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


def _stored(school, teacher, free_day):
    return TeacherPreference.objects.create(
        teacher=teacher, school=school, academic_year=YEAR, free_day=free_day
    )


def _post(client, **extra):
    payload = {"max_daily_periods": "5", "max_consecutive": "", "max_gap": "", "notes": ""}
    payload.update(extra)
    return client.post(URL, payload)


def test_a_teacher_post_cannot_set_the_free_day(client, school, teacher):
    client.force_login(teacher)
    pref = _stored(school, teacher, None)

    _post(client, free_day=str(WEDNESDAY))

    pref.refresh_from_db()
    assert pref.free_day is None


def test_a_teacher_post_cannot_clear_or_change_the_admin_free_day(client, school, teacher):
    client.force_login(teacher)
    pref = _stored(school, teacher, WEDNESDAY)

    _post(client, free_day="")
    _post(client, free_day="4")

    pref.refresh_from_db()
    assert pref.free_day == WEDNESDAY


def test_the_other_fields_still_save_without_the_free_day(client, school, teacher):
    client.force_login(teacher)
    pref = _stored(school, teacher, WEDNESDAY)

    _post(client, max_daily_periods="4", notes="ملاحظة")

    pref.refresh_from_db()
    assert (pref.max_daily_periods, pref.notes, pref.free_day) == (4, "ملاحظة", WEDNESDAY)


def test_the_free_day_is_not_a_teacher_editable_field():
    assert "free_day" not in TeacherPreference.TEACHER_EDITABLE_FIELDS


def test_the_page_neither_shows_nor_names_the_free_day(client, school, teacher):
    """قرار المالك 10-10 (D-341م): يومُ التفريغ يُخفى كلّيّاً عن المعلّم — لا حقلَ ولا يومَ ولا نصَّ."""
    client.force_login(teacher)
    pref = _stored(school, teacher, WEDNESDAY)

    body = client.get(URL).content.decode()

    assert 'name="free_day"' not in body and "free_day" not in body
    assert "يوم التفريغ" not in body and "لا يوجد يوم تفريغ" not in body
    assert pref.get_free_day_display() not in body


def test_the_capacity_check_still_counts_the_admin_day(client, school, teacher):
    """النصابُ 4 على أربعة أيّامٍ مفتوحة يحتاج حصّةً يوميّاً — فسقفٌ يوميّ 1 يسع، ولا يتغيّر بطلب المعلّم."""
    client.force_login(teacher)
    pref = _stored(school, teacher, WEDNESDAY)

    _post(client, max_daily_periods="1", free_day="")

    pref.refresh_from_db()
    assert (pref.max_daily_periods, pref.free_day) == (1, WEDNESDAY)


def test_the_admin_change_is_audited_without_the_teacher_name(client, superuser, school, teacher):
    client.force_login(superuser)
    pref = _stored(school, teacher, None)
    url = reverse("admin:operations_teacherpreference_change", args=[pref.pk])
    data = {
        "teacher": teacher.pk,
        "school": school.pk,
        "academic_year": YEAR,
        "max_daily_periods": 5,
        "max_first_periods": 2,
        "max_last_periods": 2,
        "free_day": WEDNESDAY,
        "notes": "",
    }

    client.post(url, data, follow=True)

    pref.refresh_from_db()
    assert pref.free_day == WEDNESDAY
    entry = AuditLog.objects.get(changes__event="teacher_free_day_changed")
    assert entry.changes["before"] is None and entry.changes["after"] == WEDNESDAY
    assert entry.object_id == str(pref.pk)
    assert teacher.full_name not in entry.object_repr


def test_an_admin_save_that_leaves_the_day_alone_writes_no_free_day_audit(
    client, superuser, school, teacher
):
    client.force_login(superuser)
    pref = _stored(school, teacher, WEDNESDAY)
    url = reverse("admin:operations_teacherpreference_change", args=[pref.pk])
    data = {
        "teacher": teacher.pk,
        "school": school.pk,
        "academic_year": YEAR,
        "max_daily_periods": 4,
        "free_day": WEDNESDAY,
        "notes": "",
    }

    client.post(url, data, follow=True)

    assert not AuditLog.objects.filter(changes__event="teacher_free_day_changed").exists()


def test_the_generator_reads_the_same_stored_day(school, teacher):
    _stored(school, teacher, WEDNESDAY)

    preferences = scheduler.load_inputs(school, YEAR)[1]

    assert preferences[str(teacher.pk)]["free_day"] == WEDNESDAY

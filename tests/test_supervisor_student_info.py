"""[STUDENT-INFO][WING-SCOPE] مركزُ معلومات الطلبة للمشرف الإداريّ — جناحُه وحدَه.

قرارا المستخدم 2026-09-14 و2026-09-15 اللذان تحرسهما هذه الاختبارات:
- المشرفُ الإداريُّ يرى في المركز شُعبَ أجنحته وطلبتَها وحدهم؛ ورابطُ شعبةٍ أو طالبٍ
  من خارج جناحه يعود 404 — في القراءة والكتابة معاً، ولا يوسّعه `?year=`.
- ولا يرى وإن كان الطالبُ من جناحه: الدرجاتِ ونتائجَ الموادّ، ولا ملاحظاتِ الأخصائيّ
  الاجتماعيّ والنفسيّ.
- والمستوياتُ التعليميّةُ والأنشطةُ مغلقتان عليه (404).
- والقيادةُ والمعلّمون كما كانوا حرفاً، والبديلُ المكلَّف بالجناح لا يدخل المركز.
"""

import datetime as dt

import pytest
from django.urls import reverse

from core.models import AuditLog, Wing
from student_info.models import StudentNote
from tests.conftest import (
    ClassGroupFactory,
    MembershipFactory,
    RoleFactory,
    StudentEnrollmentFactory,
    UserFactory,
)

pytestmark = pytest.mark.django_db

OLD_YEAR = "2020-2021"


# ── العالَم: جناحان، لكلٍّ شعبةٌ وطالب ─────────────────────────────────


@pytest.fixture
def year(seeded_calendar):
    """العامُ الجاري من التقويم المبذور — قبل أيّ شعبةٍ أو جناح."""
    return seeded_calendar


def _member(school, role, name, national_id):
    user = UserFactory(full_name=name, national_id=national_id)
    MembershipFactory(user=user, school=school, role=RoleFactory(school=school, name=role))
    return user


def _student(school, klass, name, national_id):
    student = _member(school, "student", name, national_id)
    StudentEnrollmentFactory(student=student, class_group=klass)
    return student


@pytest.fixture
def supervisor(school, year):
    return _member(school, "admin_supervisor", "مشرف الجناح الأوّل", "29400000001")


@pytest.fixture
def other_supervisor(school, year):
    return _member(school, "admin_supervisor", "مشرف الجناح الثاني", "29400000002")


@pytest.fixture
def klass(school, year, supervisor):
    wing = Wing.objects.create(
        school=school, code="w1", name="جناح 1", academic_year=year, supervisor=supervisor
    )
    return ClassGroupFactory(
        school=school, grade="G7", section="1", level_type="prep", academic_year=year, wing=wing
    )


@pytest.fixture
def other_klass(school, year, other_supervisor):
    wing = Wing.objects.create(
        school=school, code="w2", name="جناح 2", academic_year=year, supervisor=other_supervisor
    )
    return ClassGroupFactory(
        school=school, grade="G8", section="2", level_type="prep", academic_year=year, wing=wing
    )


@pytest.fixture
def mine(school, klass):
    return _student(school, klass, "طالب جناحي", "29400000011")


@pytest.fixture
def theirs(school, other_klass):
    return _student(school, other_klass, "طالب الجناح الآخر", "29400000012")


def _note(school, student, category, author, year, title):
    return StudentNote.objects.create(
        school=school,
        student=student,
        category=category,
        title=title,
        body="نصُّ الملاحظة.",
        occurred_on=dt.date(2026, 9, 14),
        academic_year=year,
        created_by=author,
    )


def _get(client, user, name, *args, **query):
    client.force_login(user)
    url = reverse(name, args=args)
    if query:
        url += "?" + "&".join(f"{k}={v}" for k, v in query.items())
    return client.get(url)


# ── الحدُّ في الوحدة نفسها ─────────────────────────────────────────────


def test_the_supervisor_enters_the_centre_but_no_longer_reads_the_whole_school():
    from student_info.access import MODULE_ROLES, SCHOOL_WIDE_READERS

    assert "admin_supervisor" not in SCHOOL_WIDE_READERS
    assert "admin_supervisor" in MODULE_ROLES


def test_wing_substitutes_are_not_given_the_centre():
    """البديلُ المكلَّف بالجناح يرصد كشفَه — ولا يأخذ مركزَ المعلومات (قرار 2026-09-15)."""
    from student_info.access import MODULE_ROLES

    assert not {"student_observer", "services_worker"} & set(MODULE_ROLES)


def test_can_read_student_follows_the_wing(supervisor, school, year, mine, theirs):
    from student_info.access import can_read_student

    assert can_read_student(supervisor, mine, school, year)
    assert not can_read_student(supervisor, theirs, school, year)


def test_a_substitute_holding_a_wing_reads_nothing_through_the_centre(school, year, klass, mine):
    from student_info.access import can_read_student, visible_class_groups

    observer = _member(school, "student_observer", "ملاحظ الطلبة", "29400000031")

    assert not can_read_student(observer, mine, school, year)
    assert not visible_class_groups(observer, school, year).exists()


def test_a_substitute_is_turned_away_at_the_door(client, school, year):
    observer = _member(school, "student_observer", "ملاحظ الطلبة", "29400000032")

    response = _get(client, observer, "student_info:sections")

    assert response.status_code in (302, 403)


# ── الشُّعب ────────────────────────────────────────────────────────────


def test_the_sections_page_shows_the_supervisor_his_wing_only(
    client, supervisor, principal_user, klass, other_klass
):
    mine_shown = {g.id for g in _get(client, supervisor, "student_info:sections").context["groups"]}
    all_shown = {
        g.id for g in _get(client, principal_user, "student_info:sections").context["groups"]
    }

    assert mine_shown == {klass.id}
    assert {klass.id, other_klass.id} <= all_shown


def test_an_old_year_does_not_widen_the_supervisors_sections(
    client, school, supervisor, principal_user, klass
):
    old = ClassGroupFactory(school=school, grade="G9", section="1", academic_year=OLD_YEAR)

    supervisor_page = _get(client, supervisor, "student_info:sections", year=OLD_YEAR)
    principal_page = _get(client, principal_user, "student_info:sections", year=OLD_YEAR)

    assert {g.id for g in supervisor_page.context["groups"]} == {klass.id}
    assert supervisor_page.context["year"] != OLD_YEAR
    # والقيادةُ تبقى تتصفّح الأعوامَ كما كانت.
    assert {g.id for g in principal_page.context["groups"]} == {old.id}


def test_levels_and_activities_buttons_are_hidden_from_the_supervisor(
    client, supervisor, principal_user, klass
):
    levels = reverse("student_info:levels")

    assert levels not in _get(client, supervisor, "student_info:sections").content.decode()
    assert levels in _get(client, principal_user, "student_info:sections").content.decode()


def test_a_section_outside_the_wing_is_404(client, supervisor, klass, other_klass, mine, theirs):
    outside = _get(client, supervisor, "student_info:section_students", other_klass.id)
    response = _get(client, supervisor, "student_info:section_students", klass.id)

    assert outside.status_code == 404
    assert response.status_code == 200
    assert [e.student_id for e in response.context["enrollments"]] == [mine.id]


def test_a_teacher_outside_his_classes_is_still_redirected(client, teacher_user, klass):
    response = _get(client, teacher_user, "student_info:section_students", klass.id)

    assert response.status_code == 302


def test_a_student_moved_to_another_wing_leaves_the_old_section_list(
    client, school, supervisor, klass, other_klass, mine
):
    """قيدان نشطان: القديمُ في جناحه والجاري في غيره — فالطالبُ لجناحه الجاري وحدَه."""
    mine.enrollments.filter(class_group=klass).update(enrolled_at=dt.date(2026, 9, 1))
    StudentEnrollmentFactory(
        student=mine, class_group=other_klass, enrolled_at=dt.date(2026, 9, 10)
    )

    section = _get(client, supervisor, "student_info:section_students", klass.id)
    file_page = _get(client, supervisor, "student_info:student_file", mine.id)

    assert list(section.context["enrollments"]) == []
    assert file_page.status_code == 404


# ── ملفُّ الطالب ────────────────────────────────────────────────────────


def test_a_file_outside_the_wing_is_404(client, supervisor, theirs):
    plain = _get(client, supervisor, "student_info:student_file", theirs.id)
    with_year = _get(client, supervisor, "student_info:student_file", theirs.id, year=OLD_YEAR)

    assert plain.status_code == 404
    assert with_year.status_code == 404


def test_a_staff_members_id_is_404_to_the_supervisor(client, supervisor, teacher_user, klass):
    assert _get(client, supervisor, "student_info:student_file", teacher_user.id).status_code == 404


def test_the_supervisor_reads_his_students_file_without_grades_or_specialist_notes(
    client, school, year, supervisor, mine, psychologist_user, social_worker_user, nurse_user
):
    _note(school, mine, "psychologist", psychologist_user, year, "ملاحظة نفسية سرية")
    _note(school, mine, "social_worker", social_worker_user, year, "ملاحظة اجتماعية سرية")
    _note(school, mine, "nurse", nurse_user, year, "ملاحظة الممرض")

    response = _get(client, supervisor, "student_info:student_file", mine.id)
    body = response.content.decode()

    assert response.status_code == 200
    assert response.context["shows_grades"] is False
    assert response.context["results"] == []
    assert response.context["average"] is None
    assert "التحصيل ومستواه" not in body
    assert [g["key"] for g in response.context["note_groups"]] == ["teacher", "student_affairs"]
    assert "سرية" not in body
    # ملاحظةُ الممرّض تحمل سببَ زيارة العيادة — والمشرفُ لا يرى من العيادة إلّا التاريخ (القرار 3).
    assert "ملاحظة الممرض" not in body
    # ما لم يُقرأ لا يُسجَّل قراءةً.
    assert not AuditLog.objects.filter(model_name="StudentNote", user=supervisor).exists()


def test_the_principal_still_reads_the_whole_file(
    client, school, year, principal_user, mine, psychologist_user
):
    _note(school, mine, "psychologist", psychologist_user, year, "ملاحظة نفسية")

    response = _get(client, principal_user, "student_info:student_file", mine.id)

    assert response.status_code == 200
    assert response.context["shows_grades"] is True
    assert "التحصيل ومستواه" in response.content.decode()
    assert len(response.context["note_groups"]) == 5
    assert AuditLog.objects.filter(model_name="StudentNote", user=principal_user).exists()


# ── الكتابة ────────────────────────────────────────────────────────────


def _note_form(category="student_affairs"):
    return {
        "category": category,
        "title": "تأخّر متكرّر",
        "body": "أُبلغ وليُّ الأمر.",
        "occurred_on": "2026-09-14",
    }


def test_writing_on_a_student_outside_the_wing_is_404(client, supervisor, theirs):
    client.force_login(supervisor)
    url = reverse("student_info:note_create", args=[theirs.id])

    assert client.get(url).status_code == 404
    assert client.post(url, _note_form()).status_code == 404
    assert not StudentNote.objects.exists()


def test_the_supervisor_writes_in_the_current_year_whatever_the_link_says(
    client, year, supervisor, mine
):
    client.force_login(supervisor)
    url = reverse("student_info:note_create", args=[mine.id]) + f"?year={OLD_YEAR}"

    response = client.post(url, _note_form())

    assert response.status_code == 302
    note = StudentNote.objects.get(student=mine)
    assert note.academic_year == year
    assert note.category == "student_affairs"
    assert note.created_by == supervisor


def test_the_supervisor_may_not_write_a_specialist_note(client, supervisor, mine):
    client.force_login(supervisor)
    url = reverse("student_info:note_create", args=[mine.id])

    client.post(url, _note_form("psychologist"))

    assert not StudentNote.objects.exists()


# ── قوائمُ الملاحظات ────────────────────────────────────────────────────


def test_the_notes_list_is_narrowed_to_the_wing_before_counting(
    client, school, year, supervisor, principal_user, mine, theirs
):
    _note(school, mine, "student_affairs", supervisor, year, "ملاحظة جناحي")
    _note(school, theirs, "student_affairs", principal_user, year, "ملاحظة الجناح الآخر")

    response = _get(client, supervisor, "student_info:notes", "student_affairs", year=OLD_YEAR)
    everyone = _get(client, principal_user, "student_info:notes", "student_affairs")

    assert response.status_code == 200
    assert response.context["page"].paginator.count == 1
    assert [n.student_id for n in response.context["page"].object_list] == [mine.id]
    assert everyone.context["page"].paginator.count == 2


@pytest.mark.parametrize("category", ["social_worker", "psychologist"])
def test_specialist_note_lists_are_404_to_the_supervisor(
    client, school, year, supervisor, principal_user, mine, category
):
    _note(school, mine, category, principal_user, year, "ملاحظة")

    assert _get(client, supervisor, "student_info:notes", category).status_code == 404
    assert _get(client, principal_user, "student_info:notes", category).status_code == 200
    assert not AuditLog.objects.filter(model_name="StudentNote", user=supervisor).exists()


# ── ما ليس من مهامّه ─────────────────────────────────────────────────


@pytest.mark.parametrize("url_name", ["student_info:levels", "student_info:activities"])
def test_levels_and_activities_are_closed_to_the_supervisor(
    client, supervisor, principal_user, klass, url_name
):
    assert _get(client, supervisor, url_name).status_code == 404
    assert _get(client, principal_user, url_name).status_code == 200

"""شاشةُ توزيعات المواد على الشُّعب: المنسّقُ مدرِّس، ومَن خارج القائمة لا يُمحى.

كان اثنا عشرَ منسّقاً يحملون ستّين حصّةً بعضويّة `coordinator` وحدها، وقائمةُ
المعلّمين في الشاشة تقبل دورَ `teacher` حرفيّاً — فتعرض صفوفَهم «— بلا معلّم —»
والرأسُ يقول «0 بلا معلّم»، وحفظُ الصفّ يُرسل معلّماً فارغاً فيمحو الإسناد بصمت.

الأدوارُ المدرِّسةُ هنا قرارٌ لا اجتهاد (2026-09-02): معلّمٌ ومنسّق.
"""

import pytest
from django.urls import reverse

from core.models import ClassGroup, CustomUser
from tests.conftest import MembershipFactory, RoleFactory, UserFactory

YEAR = "2026-2027"


def _staff(school, role_name, name):
    user = UserFactory(full_name=name)
    MembershipFactory(user=user, school=school, role=RoleFactory(school=school, name=role_name))
    return user


@pytest.fixture
def cell(db, school):
    """شعبةٌ ومادّة — خليّةُ إسنادٍ واحدة."""
    from operations.models import Subject

    group = ClassGroup.objects.create(
        school=school, grade="G12", section="1", level_type="sec", academic_year=YEAR
    )
    subject = Subject.objects.create(school=school, name_ar="الرياضيات", code="MAT")
    return group, subject


def _assign(school, cell, teacher, periods=6):
    from operations.models import SubjectClassAssignment

    group, subject = cell
    return SubjectClassAssignment.objects.create(
        school=school,
        class_group=group,
        subject=subject,
        teacher=teacher,
        weekly_periods=periods,
        academic_year=YEAR,
    )


def _page(client_as, user):
    resp = client_as(user).get(reverse("subject_assignments") + f"?year={YEAR}")
    assert resp.status_code == 200
    return resp.content.decode()


def _save(client, assignment, **fields):
    data = {"year": YEAR, "weekly_periods": assignment.weekly_periods, "parallel_group": ""}
    data.update(fields)
    resp = client.post(reverse("subject_assignment_edit", args=[assignment.id]), data)
    assert resp.status_code == 302
    assignment.refresh_from_db()
    return assignment


# ══════════════════════════════════════════════════════════════════════
#  ١. مَن يُعدّ مدرِّساً
# ══════════════════════════════════════════════════════════════════════


def test_teaching_roles_are_teacher_and_coordinator_only(
    school, teacher_user, coordinator_user, ese_teacher_user, activities_coordinator_user
):
    """المنسّقُ يدرّس بنصابٍ مخفَّض فهو في القائمة — وغيرُهما خارجها بقرار."""
    listed = set(CustomUser.objects.teachers(school))
    assert {teacher_user, coordinator_user} <= listed
    assert ese_teacher_user not in listed
    assert activities_coordinator_user not in listed


def test_a_departed_coordinator_is_not_offered(school, coordinator_user):
    """العضويّةُ المُطفأة تُخرج صاحبَها من القائمة — كما تُخرج المعلّم."""
    coordinator_user.memberships.update(is_active=False)
    assert coordinator_user not in set(CustomUser.objects.teachers(school))


# ══════════════════════════════════════════════════════════════════════
#  ٢. الصفُّ يقول ما تقوله القاعدة
# ══════════════════════════════════════════════════════════════════════


def test_coordinator_row_shows_their_name_and_counts_as_staffed(
    client_as, principal_user, school, coordinator_user, cell
):
    """صفُّ المنسّق يختاره بالاسم، والرأسُ والصفُّ يتّفقان: لا «بلا معلّم»."""
    _assign(school, cell, coordinator_user)
    html = _page(client_as, principal_user)
    assert "0 بلا معلّم" in html
    assert f'value="{coordinator_user.id}" selected' in html
    assert "خارج قائمة" not in html


def test_a_teacher_outside_the_list_is_shown_by_name_not_as_unstaffed(
    client_as, principal_user, school, cell
):
    """نائبٌ أكاديميٌّ أُسنِدت له حصص: ليس في القائمة، لكنّ اسمَه يظهر مختاراً."""
    vice = _staff(school, "vice_academic", "النائب الأكاديمي المدرِّس")
    _assign(school, cell, vice)
    html = _page(client_as, principal_user)
    assert "0 بلا معلّم" in html
    assert f'value="{vice.id}" selected' in html
    assert vice.full_name in html
    assert "خارج قائمة المدرِّسين" in html


# ══════════════════════════════════════════════════════════════════════
#  ٣. الحفظُ لا يمحو إلّا ما قُصد محوُه
# ══════════════════════════════════════════════════════════════════════


def test_saving_a_row_keeps_a_teacher_who_is_outside_the_list(
    client_as, principal_user, school, cell
):
    """تعديلُ الحصص على صفٍّ معلّمُه خارج القائمة يُبقي المعلّمَ كما هو."""
    vice = _staff(school, "vice_academic", "النائب الأكاديمي المدرِّس")
    a = _assign(school, cell, vice, periods=6)
    a = _save(client_as(principal_user), a, teacher=str(vice.id), weekly_periods=3)
    assert a.teacher_id == vice.id
    assert a.weekly_periods == 3


def test_a_coordinator_can_be_assigned_from_the_row(
    client_as, principal_user, school, coordinator_user, cell
):
    """توزيعٌ بلا معلّم يُسنَد إلى منسّقٍ من الصفّ — وكان يُرفض «ليس من معلّمي مدرستك»."""
    a = _assign(school, cell, None)
    a = _save(client_as(principal_user), a, teacher=str(coordinator_user.id))
    assert a.teacher_id == coordinator_user.id


def test_a_stranger_is_still_refused(client_as, principal_user, school, coordinator_user, cell):
    """التغييرُ إلى مَن ليس مدرِّساً يُرفض ويبقى الإسنادُ القديم."""
    nurse = _staff(school, "nurse", "ممرّض المدرسة")
    a = _assign(school, cell, coordinator_user)
    a = _save(client_as(principal_user), a, teacher=str(nurse.id))
    assert a.teacher_id == coordinator_user.id


def test_an_explicit_empty_teacher_unassigns(
    client_as, principal_user, school, coordinator_user, cell
):
    """الفراغُ الصريح تفريغٌ مقصود — لا يُمنع، ويظهر في الرأس بعدها."""
    a = _assign(school, cell, coordinator_user)
    a = _save(client_as(principal_user), a, teacher="")
    assert a.teacher_id is None
    assert "1 بلا معلّم" in _page(client_as, principal_user)

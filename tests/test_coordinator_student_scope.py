"""منسقُ شؤون الطلبة يرى طلابَ المدرسة كلَّهم (W-20261018-002، بأمر المالك 2026-10-18).

كان الدورُ خارج `ALL_STUDENTS_ROLES` فيُعامَل معلّماً بلا فصول، فيعود `get_teacher_student_ids` مجموعةً فارغة
وتظهر لوحتُه بلا بيانات. الانحدارُ هنا: المنسّقُ `None` (كلُّ الطلاب)، والمعلّمُ العاديّ يبقى على فصوله.
"""

import pytest

from core.permissions import get_teacher_student_ids
from tests.conftest import MembershipFactory, RoleFactory, UserFactory

pytestmark = pytest.mark.django_db


def _staff(school, role):
    user = UserFactory(full_name=f"{role} test")
    MembershipFactory(user=user, school=school, role=RoleFactory(school=school, name=role))
    return user


def test_student_affairs_coordinator_sees_every_student(school):
    coordinator = _staff(school, "student_affairs_coordinator")
    assert get_teacher_student_ids(coordinator) is None


def test_ordinary_teacher_stays_scoped_to_own_classes(school):
    teacher = _staff(school, "teacher")
    ids = get_teacher_student_ids(teacher)
    assert ids is not None and len(ids) == 0


def test_the_role_is_listed_once_in_the_all_students_set():
    import pathlib

    text = (pathlib.Path(__file__).resolve().parent.parent / "core" / "permissions.py").read_text(
        encoding="utf-8"
    )
    block = text.split("ALL_STUDENTS_ROLES = {", 1)[1].split("}", 1)[0]
    assert block.count('"student_affairs_coordinator"') == 1

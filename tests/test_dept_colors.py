"""لونُ القسم مصدرُه واحد — `core/dept_colors.py` — تقرؤه شاشةُ الإسناد وقائمةُ الزيارة الصفّيّة.

كانت قائمةُ الزيارة تحمل نسخةً ثانيةً من الخريطة تخالف الجدولَ العامَّ في `science_sec`
(علومٌ عندها، أحياءُ في الجدول). فصار الحارسُ أنّ القائمةَ تُجيب بما يُجيب به القاموسُ المركزيّ.
"""

import pytest

from core.dept_colors import DEPT_KEY_OF_CODE, OTHER, dept_key
from quality.observation_selectors import teacher_picker_groups

pytestmark = pytest.mark.django_db


def test_the_observation_picker_uses_the_central_colour_of_a_department(school):
    from core.models import Department
    from tests.conftest import MembershipFactory, RoleFactory, UserFactory

    role = RoleFactory(school=school, name="teacher")
    teachers = []
    for code, name in (("science_sec", "علوم ثانوي"), ("DEP-XYZ", "قسم مجهول")):
        dept = Department.objects.create(school=school, name=name, code=code, sort_order=1)
        teacher = UserFactory(full_name=f"معلّم {name}")
        MembershipFactory(user=teacher, school=school, role=role, department_obj=dept)
        teachers.append(teacher)

    colours = {g["name"]: g["css_class"] for g in teacher_picker_groups(school, teachers)}

    assert colours["علوم ثانوي"] == dept_key("science_sec") == "biology"
    assert colours["قسم مجهول"] == OTHER


def test_every_mapped_key_has_a_central_dot_class():
    """لا مفتاحَ في القاموس بلا صنف `dept-{مفتاح}` في CSS المركزيّ — وإلّا لُوِّن بلا لون."""
    from tests.css_source import read_css

    css = read_css()
    for key in set(DEPT_KEY_OF_CODE.values()) | {OTHER}:
        assert f".dept-{key} " in css, key

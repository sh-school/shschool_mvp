"""[SECURITY] قوائمُ اختيار «موظّف» لا تعرض الطلبةَ ولا أولياءَ الأمور.

كانت أربعُ شاشاتٍ (منفِّذو الخطّة التشغيليّة، ولجنتا المراجعة والمنفِّذين، ومشرفو الاختبار) تجلب كلَّ عضويّةٍ فاعلةٍ في المدرسة،
فيظهر فيها الطالبُ ووليُّ الأمر باسمَيهما — عرضُ بياناتٍ شخصيّةٍ بلا حاجة (PDPPL: تقليلُ البيانات).
والمنفذُ `staff_affairs.selectors.staff_memberships` يستثني الدورَين.
"""

from datetime import date, timedelta

import pytest
from django.urls import reverse

from exam_control.models import ExamSession
from tests.conftest import MembershipFactory, RoleFactory, UserFactory

pytestmark = pytest.mark.django_db

STUDENT_NAME = "طالبٌ_لا_يُعرض_في_قوائم_الكادر"
PARENT_NAME = "وليُّ_أمرٍ_لا_يُعرض_في_قوائم_الكادر"


@pytest.fixture
def non_staff(school):
    for name, label in (("student", STUDENT_NAME), ("parent", PARENT_NAME)):
        MembershipFactory(
            user=UserFactory(full_name=label),
            school=school,
            role=RoleFactory(school=school, name=name),
        )


@pytest.fixture
def exam_session(school, principal_user):
    return ExamSession.objects.create(
        school=school,
        name="اختبار",
        session_type="final",
        academic_year="2025-2026",
        start_date=date.today(),
        end_date=date.today() + timedelta(days=14),
        created_by=principal_user,
    )


def _pages(exam_session):
    return [
        reverse("executor_mapping"),
        reverse("quality_committee"),
        reverse("executor_committee"),
        reverse("exam_control:supervisors", args=[exam_session.pk]),
    ]


def test_no_staff_picker_lists_a_student_or_a_parent(
    client_as, principal_user, teacher_user, non_staff, exam_session
):
    client = client_as(principal_user)
    for url in _pages(exam_session):
        response = client.get(url, {"year": "2025-2026"})
        assert response.status_code == 200, url
        html = response.content.decode()
        assert STUDENT_NAME not in html, url
        assert PARENT_NAME not in html, url


def test_the_staff_picker_still_lists_a_teacher(
    client_as, principal_user, teacher_user, non_staff, exam_session
):
    html = (
        client_as(principal_user)
        .get(reverse("exam_control:supervisors", args=[exam_session.pk]))
        .content.decode()
    )
    assert teacher_user.full_name in html

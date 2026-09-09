"""[SCHEDULE] مطوّرُ المنصّة في قدرات الأنصبة — دوراً لا صفةَ حساب.

    `is_superuser` صفةُ حسابٍ، و`platform_developer` دورٌ في مدرسة.

كان المطوّرُ يمرّ إلى شاشة الإسناد بصفة `is_superuser` وحدَها. وحسابُ مطوّرٍ
بلا تلك الصفة يُردّ عن شاشةٍ هي عملُه، والتدقيقُ لا يقرأ من أين جاءت القدرة.
فصار الدورُ مذكوراً صراحةً في القدرات الثلاث، ومحصَّناً من تهيئةٍ مدرسيّةٍ
تُقصيه — كما حُصّن في `TIER_SYSTEM` قبله.

ولا يعني ذلك فتحَ المعتمَد: `_may_write` تقفل الخطّةَ الموقَّعةَ على الجميع،
وتُفتح بإصدارٍ جديدٍ لا بالكتابة فوقها.
"""

import pytest

from academic_management import workload_workflow as flow
from academic_management.models import WorkloadGovernance
from tests.conftest import MembershipFactory, RoleFactory, UserFactory

pytestmark = pytest.mark.django_db

CAPS = (flow.EDIT, flow.REVIEW, flow.APPROVE)


@pytest.fixture
def developer(school):
    """مطوّرٌ بلا `is_superuser` — فالقدرةُ تُقرأ من دوره لا من صفة حسابه."""
    user = UserFactory(full_name="مطوّرُ المنصّة", is_superuser=False)
    MembershipFactory(
        user=user, school=school, role=RoleFactory(school=school, name="platform_developer")
    )
    return user


@pytest.fixture
def maths_teacher(school):
    user = UserFactory(full_name="معلّمُ الرياضيات", is_superuser=False)
    MembershipFactory(user=user, school=school, role=RoleFactory(school=school, name="teacher"))
    return user


def test_the_developer_holds_all_three(school, developer):
    assert all(flow.has_capability(developer, school, cap) for cap in CAPS)


def test_a_school_config_may_not_lock_the_developer_out(school, developer):
    """الحاسمُ: التهيئةُ تُبدّل الأدوارَ ولا تُلغي من يُصلح النظام."""
    governance = WorkloadGovernance.for_school(school)
    governance.edit_roles = ["coordinator"]
    governance.review_roles = ["vice_academic"]
    governance.approve_roles = ["principal"]
    governance.save()

    assert all(flow.has_capability(developer, school, cap) for cap in CAPS)


def test_a_teacher_still_holds_none(school, maths_teacher):
    """حسابُ المعلّم لا يرث شيئاً — والحسابان لصاحبٍ واحدٍ يبقيان مفترقَين."""
    assert not any(flow.has_capability(maths_teacher, school, cap) for cap in CAPS)


def test_the_developer_sees_every_department(school, developer):
    """نطاقُه غيرُ محدود: `review` تكفي ليتجاوز حدَّ القسم في شاشة الإسناد."""
    assert flow.has_capability(developer, school, flow.REVIEW)

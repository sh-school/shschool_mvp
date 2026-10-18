"""قدراتُ «منسّق شؤون الطلبة» في السلوك — W-20261008-009 (حارسٌ بعد W-20261001-020).

القياسُ (2026-10-18، `registry()` على main): يملك الدورُ قدرتَي `behavior.record` و`behavior.summon_parent`
اليومَ (BEHAVIOR_RECORD في `core/permissions.py`، و`family_callers` في `core/capabilities.py`) — فالبطاقةُ
حارسٌ يثبّتهما لا منحٌ جديد. ولا يملك `students.import_export` ولا `quality.evaluations`؛ وهما ملحقان
لا يُمنحان إلّا بنصّ المالك المسجَّل: تسليمُ 020 استثنى الاستيراد/التصدير عمداً، والتقييمُ يكتبه الرئيسُ
المباشر (م16) والمنسّقُ يتبع النائبَ الإداريّ بلا مرؤوسين. فالحارسُ هنا يفشل إن مُنحتا دون قرار.

ما لا يملكه الدورُ وقد يُسأل عنه (مقيسٌ لا مفترَض): الاستيرادُ والتصدير، والتقييمُ. ولا نقلَ ولا إلغاءَ
تفعيلٍ ولا هجرة في هذه البطاقة.
"""

import pytest

from core.capabilities import has_capability, registry
from tests.conftest import MembershipFactory, RoleFactory, UserFactory

ROLE = "student_affairs_coordinator"

#: ممنوحتان للدور على main اليوم؛ سقوطُ إحداهما يُكسر هنا لا في الشاشة.
HELD = ("behavior.record", "behavior.summon_parent")

#: ملحقان بلا نصّ مالك — يُمنحان بتعديل هذا الثابت مع القرار المسجَّل، لا بتعديل السجلّ وحدَه.
OWNER_DECISION_PENDING = ("students.import_export", "quality.evaluations")

#: أدوارٌ لا تملك القدرة — فالحارسُ يُثبت أنّ الباب لم يُفتح للجميع (المعلّمُ يسجّل المخالفةَ ولا يستدعي الوليّ).
NON_HOLDERS = (
    ("behavior.record", "student"),
    ("behavior.record", "parent"),
    ("behavior.summon_parent", "teacher"),
    ("behavior.summon_parent", "student"),
    ("behavior.summon_parent", "parent"),
)


def _user_with(school, role_name):
    user = UserFactory(full_name=f"مستخدم {role_name}")
    MembershipFactory(user=user, school=school, role=RoleFactory(school=school, name=role_name))
    return user


@pytest.mark.parametrize("key", HELD)
def test_the_registry_grants_the_role_what_it_holds_today(key):
    assert ROLE in registry()[key].expanded_roles, f"{key} سقطت من الدور"


@pytest.mark.django_db
@pytest.mark.parametrize("key", HELD)
def test_the_coordinator_holds_it(student_affairs_coordinator_user, key):
    assert has_capability(student_affairs_coordinator_user, key)


@pytest.mark.django_db
@pytest.mark.parametrize(("key", "role"), NON_HOLDERS)
def test_a_non_holder_does_not(school, key, role):
    assert not has_capability(_user_with(school, role), key), f"{role} يملك {key}"


@pytest.mark.parametrize("key", OWNER_DECISION_PENDING)
def test_the_annexes_stay_closed_until_the_owner_decides(key):
    """الاستيرادُ والتقييم: لا منحَ قبل نصّ المالك — ويُعدَّل هذا الاختبارُ بالقرار نفسِه حين يصدر."""
    assert ROLE not in registry()[key].expanded_roles, f"{key} مُنحت دون قرار مالك مسجَّل"


@pytest.mark.django_db
@pytest.mark.parametrize("key", OWNER_DECISION_PENDING)
def test_the_coordinator_cannot_use_the_annexes(student_affairs_coordinator_user, key):
    assert not has_capability(student_affairs_coordinator_user, key)


@pytest.mark.parametrize("key", HELD)
def test_every_held_capability_has_a_written_basis(key):
    """«كلُّ قدرةٍ لها أساسٌ مكتوب» — الفارغُ لا يُقبل؛ وافتراضُ المنصّة أساسٌ معلَن يُراجَع."""
    assert registry()[key].basis.strip(), f"{key} بلا أساس"

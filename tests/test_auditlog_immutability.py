"""[AUDIT] السجلُّ لا يُعدَّل ولا يُحذف — وهويّةُ فاعله تُفصَل حين يُمحى حسابُه.

    م.19 تحرس الواقعة        فلا يُبدَّل إجراءٌ ولا وقتٌ ولا تغييرات
    م.15 تحرس صاحبَ البيانات  فمن مُحي حسابُه تُفصَل هويّتُه عن السجلّ

وكان المنعُ مطلقاً، فصار حذفُ أيّ مستخدمٍ مستحيلاً: `AuditLog.user` مُعرَّفٌ
`SET_NULL`، فيحاول المحرّكُ تصفيرَه قبل الحذف فيرفع الزنادُ الاستثناء ويسقط
الطلبُ كلُّه — حتّى على حسابِ فحص. والاستثناءُ الآن واحدٌ محدود: `user_id`
إلى `NULL` وكلُّ عمودٍ آخرَ كما هو.
"""

import pytest
from django.core.exceptions import PermissionDenied
from django.db import IntegrityError, InternalError, transaction

from core.models import AuditLog

pytestmark = pytest.mark.django_db


@pytest.fixture
def school(db):
    from core.models import School

    return School.objects.create(name="مدرسة الشحانية", code="SHH-AUD")


@pytest.fixture
def actor(db, school):
    from tests.conftest import MembershipFactory, RoleFactory, UserFactory

    role = RoleFactory(school=school, name="principal")
    user = UserFactory(full_name="المدير", national_id="29011000001")
    MembershipFactory(user=user, school=school, role=role)
    return user


def an_entry(actor, school):
    AuditLog.log(
        user=actor,
        action="update",
        model_name="CustomUser",
        object_id=actor.id,
        object_repr=actor.full_name,
        changes={"الجنسية": {"من": "—", "إلى": "قطري"}},
        school=school,
    )
    return AuditLog.objects.filter(object_id=str(actor.id)).first()


# ══════════════════════════════════════════════════════════════════════
#  الواقعةُ محروسة
# ══════════════════════════════════════════════════════════════════════


def test_an_entry_cannot_be_edited(actor, school):
    entry = an_entry(actor, school)

    with pytest.raises((PermissionDenied, InternalError, IntegrityError)), transaction.atomic():
        AuditLog.objects.filter(pk=entry.pk).update(action="delete")


def test_an_entry_cannot_be_deleted(actor, school):
    entry = an_entry(actor, school)

    with pytest.raises((PermissionDenied, InternalError, IntegrityError)), transaction.atomic():
        AuditLog.objects.filter(pk=entry.pk).delete()


# ══════════════════════════════════════════════════════════════════════
#  والهويّةُ تُفصَل
# ══════════════════════════════════════════════════════════════════════


def test_deleting_a_user_detaches_the_actor_and_keeps_the_record(actor, school):
    """حسابُ فحصٍ يُمحى — والسجلُّ يبقى يقول ماذا جرى ومتى، بلا اسمِ فاعله."""
    entry = an_entry(actor, school)

    actor.delete()

    entry.refresh_from_db()
    assert entry.user_id is None
    assert entry.action == "update"
    assert entry.changes == {"الجنسية": {"من": "—", "إلى": "قطري"}}
    assert entry.object_repr == "المدير", "والاسمُ المكتوبُ في الوصف يبقى شاهداً"

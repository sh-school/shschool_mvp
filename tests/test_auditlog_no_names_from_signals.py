"""[W-20261003-019] مُلتقِطاتُ core/signals.py لا تكتب اسماً شخصيّاً في سجلّ التدقيق.

سجلُّ التدقيق ملحقٌ لا يُعدَّل: اسمُ طالبٍ يُكتب فيه يبقى بعد محو حسابه (م.5 بند 3 بتصحيح
0103 — النصُّ المرجعيّ ينتظر تأكيدَها). و`CustomUser.__str__` يُرجع الاسمَ الكامل، فكلُّ
`str(instance)` لمستخدمٍ أو لنموذجٍ يعرضه (ParentStudentLink وMembership…) كان يكتبه في
`object_repr` عند كلّ دخولٍ وخروجٍ وحفظ. المعرّفُ المقنَّع (النموذج + بداية pk) يكفي
المدقّقَ: يربطه بالسجلّ ولا يُعرّف شخصاً.
"""

import json

import pytest
from django.contrib.auth.signals import user_logged_in, user_logged_out
from django.test import RequestFactory

from core.audit_repr import masked_repr
from core.models import AuditLog, ParentStudentLink

from .conftest import MembershipFactory, RoleFactory, UserFactory

pytestmark = pytest.mark.django_db

NAME = "اسمٌ فريدٌ لا يتكرّر ٧٣١"


def _leaks(name=NAME):
    leaked = []
    for row in AuditLog.objects.all():
        text = row.object_repr + json.dumps(row.changes or {}, ensure_ascii=False)
        if name in text:
            leaked.append((row.action, row.model_name, row.object_repr[:40]))
    return leaked


@pytest.fixture
def person(db):
    return UserFactory(full_name=NAME)


def test_masked_repr_has_no_name_and_is_stable(person):
    text = masked_repr(person)

    assert NAME not in text
    assert str(person.pk)[:8] in text
    assert text == masked_repr(person)


def test_login_and_logout_do_not_write_the_name(person):
    request = RequestFactory().post("/login/")
    request.META["HTTP_USER_AGENT"] = "test"
    request.session = {}

    user_logged_in.send(sender=type(person), request=request, user=person)
    user_logged_out.send(sender=type(person), request=request, user=person)

    assert AuditLog.objects.filter(user=person, action__in=["login", "logout"]).count() == 2
    assert _leaks() == []


def test_saving_a_user_does_not_write_the_name(school):
    created = UserFactory(full_name=NAME)  # create
    created.is_active = False
    created.save()  # update

    assert AuditLog.objects.filter(object_id=str(created.pk)).exists()
    assert _leaks() == []


def test_membership_and_parent_link_do_not_write_the_name(school, person):
    role = RoleFactory(school=school, name="student")
    MembershipFactory(user=person, school=school, role=role)
    parent = UserFactory(full_name="ولي أمرٍ مختلف")
    ParentStudentLink.objects.create(parent=parent, student=person, school=school)

    assert AuditLog.objects.exists()
    assert _leaks() == []

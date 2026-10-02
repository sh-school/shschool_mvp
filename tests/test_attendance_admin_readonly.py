"""[LEGAL] لوحةُ الإدارة قراءةٌ فقط على سلسلة الرصد: الإدخالُ والقرارُ والرصدُ المعتمَد (W-20261002-020، L1 وحكمُ 0105).

الرصدُ سندُ خصمٍ وتأديب. فمن عدّل صفّاً من `/admin/` أفلت من الصلاحيّة والتدقيق. تمرّ هذه الاختباراتُ على
**كلّ** `ModelAdmin` و`Inline` مسجَّلٍ على النماذج الثلاثة (لا قائمةٌ يدويّة) وتثبت أنّ superuser نفسَه لا يُضيف
ولا يعدّل ولا يحذف ولا يملك إجراءً جماعيّاً.
"""

import pytest
from django.contrib import admin
from django.test import RequestFactory

from operations.models import AttendanceDecision, AttendanceEntry, StudentAttendance
from tests.conftest import UserFactory

pytestmark = pytest.mark.django_db

MODELS = (StudentAttendance, AttendanceEntry, AttendanceDecision)


@pytest.fixture
def root_request():
    request = RequestFactory().get("/admin/")
    request.user = UserFactory(full_name="superuser", national_id="29300003001", is_superuser=True)
    return request


def _admins_of(model):
    registered = admin.site._registry.get(model)
    assert registered is not None, f"{model.__name__} غيرُ مسجَّلٍ في الأدمن"
    return registered


def _inlines_on(model):
    """كلُّ Inline يعرض `model` داخل أيّ ModelAdmin مسجَّل."""
    for model_admin in admin.site._registry.values():
        for inline_class in model_admin.inlines:
            if inline_class.model is model:
                yield inline_class(model_admin.model, admin.site)


@pytest.mark.parametrize("model", MODELS)
def test_the_model_admin_is_read_only_even_for_a_superuser(model, root_request):
    model_admin = _admins_of(model)
    assert not model_admin.has_add_permission(root_request)
    assert not model_admin.has_change_permission(root_request)
    assert not model_admin.has_delete_permission(root_request)


@pytest.mark.parametrize("model", MODELS)
def test_the_model_admin_has_no_bulk_actions(model, root_request):
    """إجراءُ «حذف المحدَّد» يتجاوز has_delete_permission على بعض الإصدارات إن لم يُعطَّل."""
    model_admin = _admins_of(model)
    assert model_admin.get_actions(root_request) == {}


@pytest.mark.parametrize("model", MODELS)
def test_every_inline_showing_the_model_is_read_only(model, root_request):
    for inline in _inlines_on(model):
        assert not inline.has_add_permission(root_request, None)
        assert not inline.has_change_permission(root_request, None)
        assert not inline.has_delete_permission(root_request, None)
        assert inline.max_num == 0
        assert inline.can_delete is False
        editable = set(inline.get_fields(root_request)) - set(
            inline.get_readonly_fields(root_request)
        )
        assert not editable, f"حقولٌ قابلةٌ للتعديل في الـinline: {sorted(editable)}"

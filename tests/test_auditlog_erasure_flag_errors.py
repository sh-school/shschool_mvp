"""[W-20261012-016] متابعةُ حكم 0104 على W-20261010-053.

(أ) خطأُ SQL داخل حلقة المسح لا يخفيه خطأُ إعادة العلَم: العلَمُ محلّيٌّ للمعاملة فيزول بالتراجع،
    ولا أمرَ إضافيَّ في `finally` على معاملةٍ مُجهَضة. يخرج الخطأُ الأصليُّ كما هو.
(ب) فحصُ الاسم المشترك يقرأ `CustomUser` وحدَه لأنّه الجدولُ الوحيدُ الذي يحمل اسمَ شخصٍ في عمودٍ
    مستقل؛ وحارسٌ هنا يفشل إن أُضيف نموذجٌ آخر بحقل `full_name` فيُوسَّع الفحص بقرار.
لا أسماءَ حقيقيّةً: أسماءٌ مصطنعة.
"""

import pytest
from django.apps import apps
from django.db import DatabaseError, connection, transaction

from core.models import AuditLog

from .conftest import UserFactory

NAME = "طالب المحو الاختباري"
FLAGS = (
    "app.auditlog_network_erasure",
    "app.auditlog_name_erasure",
    "app.auditlog_changes_erasure",
)


def _flag(name):
    with connection.cursor() as cur:
        cur.execute("SELECT coalesce(current_setting(%s, true), '')", [name])
        return cur.fetchone()[0]


def _entry(**kw):
    return AuditLog.objects.create(
        action="update", model_name="CustomUser", object_id="x1", user_agent="ua", **kw
    )


@pytest.mark.django_db
class TestOriginalErrorIsNotMasked:
    def test_a_sql_failure_inside_the_loop_surfaces_as_the_original_error(self, monkeypatch):
        student = UserFactory(full_name=NAME)
        _entry(object_repr="واقعة", changes={"k": NAME})

        from django.db import models as dj_models

        def failing_update(qs, **kwargs):
            # خطأٌ حقيقيّ من القاعدة يُجهض المعاملة، لا استثناءُ بايثون عاديّ.
            with connection.cursor() as cur:
                cur.execute("SELECT 1/0")

        monkeypatch.setattr(dj_models.QuerySet, "update", failing_update)

        with pytest.raises(DatabaseError) as info:
            AuditLog.objects.anonymize_name_in_changes(student, NAME)

        assert "division by zero" in str(info.value)
        assert "current transaction is aborted" not in str(info.value)

    def test_the_flag_is_gone_after_a_failure_inside_an_outer_transaction(self, monkeypatch):
        student = UserFactory(full_name=NAME)
        _entry(object_repr="واقعة", changes={"k": NAME})
        from django.db import models as dj_models

        def failing_update(qs, **kwargs):
            with connection.cursor() as cur:
                cur.execute("SELECT 1/0")

        monkeypatch.setattr(dj_models.QuerySet, "update", failing_update)

        # المحوُ نفسُه داخل معاملةٍ أعلى (كما في خدمة المحو)؛ يلتقط المستدعي الخطأَ ويواصل.
        with transaction.atomic():
            with pytest.raises(DatabaseError):
                AuditLog.objects.anonymize_name_in_changes(student, NAME)
            assert all(_flag(f) in ("", "off") for f in FLAGS)

    def test_the_flag_is_closed_on_success_inside_an_outer_transaction(self):
        student = UserFactory(full_name=NAME)
        _entry(object_repr=NAME, changes={"k": NAME})

        with transaction.atomic():
            AuditLog.objects.anonymize_name_in_repr(student, NAME)
            AuditLog.objects.anonymize_name_in_changes(student, NAME)
            AuditLog.objects.redact_network_identity(student)
            assert all(_flag(f) in ("", "off") for f in FLAGS)

    def test_a_failure_in_the_description_step_also_surfaces_unmasked(self, monkeypatch):
        student = UserFactory(full_name=NAME)
        _entry(object_repr=NAME)
        from django.db import models as dj_models

        def failing_update(qs, **kwargs):
            with connection.cursor() as cur:
                cur.execute("SELECT 1/0")

        monkeypatch.setattr(dj_models.QuerySet, "update", failing_update)

        with pytest.raises(DatabaseError) as info:
            AuditLog.objects.anonymize_name_in_repr(student, NAME)

        assert "division by zero" in str(info.value)


def test_customuser_is_the_only_model_with_a_person_name_column():
    """نطاقُ فحص الاسم المشترك موثَّق: إن ظهر نموذجٌ آخر بحقل اسمٍ شخصيّ فليُوسَّع الفحصُ بقرار."""
    holders = sorted(
        model._meta.label
        for model in apps.get_models()
        if any(field.name == "full_name" for field in model._meta.get_fields())
    )
    assert holders == ["core.CustomUser"]

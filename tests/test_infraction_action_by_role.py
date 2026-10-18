"""الإجراءُ التأديبيّ عند تسجيل المخالفة يُصفّى بالدور — W-20261001-022.

السند: بطاقةُ المشرف الإداريّ في `03_job_descriptions_rbac.md` («رصد المخالفات وتحويلها للأخصائي
الاجتماعي»)، وسياسةُ السلوك (08_conduct_policy_2026.md): التعهّدُ الخطّيّ للطالب «إحالة لمنسق شؤون
الطلبة | منسق شؤون الطلبة»، وللمشرف «تنبيه شفهي + إشعار ولي الأمر هاتفياً». فالمشرفُ لا يفرض جزاءً.
والإشعارُ: وليُّ الأمر يُشعَر تلقائياً بتسجيل المخالفة (ليس خياراً في القائمة) — افتراضٌ معلَن.
"""

import pytest
from django.urls import reverse

from behavior.forms import (
    DISCIPLINARY_ACTION_CHOICES,
    InfractionForm,
    action_choices_for,
)
from behavior.models import BehaviorInfraction
from tests.test_period_register import klass, supervisor, teacher, year  # noqa: F401
from tests.test_supervisor_behavior_scope import (  # noqa: F401
    _record_payload,
    mine,
    principal,
)

pytestmark = pytest.mark.django_db

ALLOWED_FOR_SUPERVISOR = {"verbal_warning", "social_specialist_referral"}
ALL_ACTIONS = {value for value, _ in DISCIPLINARY_ACTION_CHOICES if value}
FORBIDDEN_FOR_SUPERVISOR = ALL_ACTIONS - ALLOWED_FOR_SUPERVISOR


class TestTheChoices:
    def test_the_supervisor_sees_only_the_three_non_penal_ones(self):
        values = {value for value, _ in action_choices_for("admin_supervisor") if value}
        assert values == ALLOWED_FOR_SUPERVISOR

    @pytest.mark.parametrize("role", ["principal", "vice_admin", "social_worker", "teacher", None])
    def test_everyone_else_keeps_the_full_list(self, role):
        assert action_choices_for(role) == list(DISCIPLINARY_ACTION_CHOICES)


class TestTheServerRefuses:
    @pytest.mark.parametrize("action", sorted(FORBIDDEN_FOR_SUPERVISOR))
    def test_the_form_rejects_a_penalty_from_the_supervisor(self, action):
        form = InfractionForm(
            {
                "student_id": "7d9f6d52-0d7c-4f67-a8bb-3a3f1d5d2c11",
                "level": 1,
                "disciplinary_action_type": action,
                "violation_description": "وصفٌ كافٍ للمحضر في هذه الحالة التجريبيّة",
            },
            role="admin_supervisor",
        )
        assert not form.is_valid()
        assert "ليس من صلاحية دورك" in form.errors["disciplinary_action_type"][0]

    @pytest.mark.parametrize("action", sorted(FORBIDDEN_FOR_SUPERVISOR))
    def test_the_view_writes_nothing_when_the_supervisor_forces_a_penalty(
        self, client_as, school, seeded_calendar, mine, supervisor, action
    ):
        """لو عدّل الطلبَ يدوياً (الواجهةُ للإرشاد والخادمُ للحكم): لا مخالفةَ تُكتب."""
        before = BehaviorInfraction.objects.count()
        payload = {
            **_record_payload(mine),
            "disciplinary_action_type": action,
            "violation_description": "وصفٌ كافٍ للمحضر في هذه الحالة التجريبيّة",
        }
        client_as(supervisor).post(reverse("behavior:report_infraction"), payload)
        assert BehaviorInfraction.objects.count() == before

    @pytest.mark.parametrize("action", sorted(ALLOWED_FOR_SUPERVISOR))
    def test_the_supervisor_can_still_record_an_allowed_action(
        self, client_as, school, seeded_calendar, mine, supervisor, action
    ):
        payload = {**_record_payload(mine), "disciplinary_action_type": action}
        client_as(supervisor).post(reverse("behavior:report_infraction"), payload)
        saved = BehaviorInfraction.objects.get(student=mine)
        assert saved.disciplinary_action_type == action


class TestOthersAreUnchanged:
    def test_the_principal_may_still_choose_a_pledge(
        self, client_as, school, seeded_calendar, mine, principal
    ):
        payload = {**_record_payload(mine), "disciplinary_action_type": "written_pledge"}
        client_as(principal).post(reverse("behavior:report_infraction"), payload)
        assert BehaviorInfraction.objects.get(student=mine).disciplinary_action_type == (
            "written_pledge"
        )

    def test_the_form_page_lists_only_the_allowed_options_for_the_supervisor(
        self, client_as, school, seeded_calendar, supervisor
    ):
        html = client_as(supervisor).get(reverse("behavior:report_infraction")).content.decode()
        for action in ALLOWED_FOR_SUPERVISOR:
            assert f'value="{action}"' in html
        for action in FORBIDDEN_FOR_SUPERVISOR:
            assert f'<option value="{action}"' not in html

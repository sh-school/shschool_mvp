"""تكليفُ موظّفٍ بدورٍ غيرِ دور مسمّاه — الأمرُ يكتب ما قُرّر، ولا يكتب ما لم يُقرَّر.

والحالةُ التي كُتب لها: موظّفٌ مسمّاه «ملاحظ طلبة» أسنده المديرُ مشرفَ نقل. فدورُه
`bus_supervisor` ومسمّاه يبقى حيث يُقرأ.
"""

from io import StringIO

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from core.models import Membership, PermissionAuditLog
from tests.conftest import MembershipFactory, RoleFactory, UserFactory

REFERENCE = "قرار مدير المدرسة 2026/17 بتاريخ 2026-09-12"


@pytest.fixture
def observer(db, school):
    role = RoleFactory(school=school, name="student_observer")
    user = UserFactory(full_name="ملاحظٌ مكلَّف", employee_number="900017")
    MembershipFactory(user=user, school=school, role=role, job_title="ملاحظ طلبة")
    return user


def _run(school, **overrides):
    options = {
        "school": school.code,
        "employee_number": "900017",
        "role": "bus_supervisor",
        "reference": REFERENCE,
    }
    options.update(overrides)
    out = StringIO()
    call_command("reassign_staff_role", stdout=out, **options)
    return out.getvalue()


def _membership(user):
    return Membership.objects.select_related("role").get(user=user, is_active=True)


class TestItWritesOnlyWhenAsked:
    def test_without_apply_nothing_changes(self, school, observer):
        output = _run(school)
        assert _membership(observer).role.name == "student_observer"
        assert "لم يُكتب شيء" in output

    def test_apply_changes_the_role_and_keeps_the_ministry_title(self, school, observer):
        _run(school, apply=True)
        membership = _membership(observer)
        assert membership.role.name == "bus_supervisor"
        assert membership.job_title == "ملاحظ طلبة", "المسمّى الوزاريُّ يبقى حيث يُقرأ"
        assert membership.appointment_reference == REFERENCE

    def test_apply_leaves_an_audit_line(self, school, observer):
        _run(school, apply=True)
        entry = PermissionAuditLog.objects.get(target=observer, action="role_assigned")
        assert entry.details["from"] == "student_observer"
        assert entry.details["to"] == "bus_supervisor"
        assert entry.details["reference"] == REFERENCE

    def test_running_twice_changes_nothing_the_second_time(self, school, observer):
        _run(school, apply=True)
        output = _run(school, apply=True)
        assert "لا تغيير" in output
        assert PermissionAuditLog.objects.filter(target=observer).count() == 1

    def test_the_user_now_reads_as_the_new_role(self, school, observer):
        _run(school, apply=True)
        observer.refresh_from_db()
        observer.invalidate_active_membership()
        assert observer.get_role() == "bus_supervisor"


class TestItRefusesWhatIsNotDecided:
    @pytest.mark.parametrize(
        "reference",
        ["", "قرار", "قرار مدير المدرسة رقم ... بتاريخ ...", "<المرجع هنا>", "TODO later"],
    )
    def test_a_missing_or_placeholder_reference_fails(self, school, observer, reference):
        with pytest.raises(CommandError):
            _run(school, reference=reference, apply=True)
        assert _membership(observer).role.name == "student_observer"

    def test_a_beneficiary_role_is_refused(self, school, observer):
        with pytest.raises(CommandError, match="ليس دورَ كادر"):
            _run(school, role="parent", apply=True)

    def test_an_unknown_employee_number_is_refused(self, school, observer):
        with pytest.raises(CommandError, match="لا موظّفَ"):
            _run(school, employee_number="000000", apply=True)

    def test_two_staff_memberships_are_ambiguous(self, school, observer):
        """لا يُعرف أيُّ العضويّتين يُغيَّر — فلا يُغيَّر شيء."""
        MembershipFactory(
            user=observer, school=school, role=RoleFactory(school=school, name="services_worker")
        )
        with pytest.raises(CommandError, match="لا يُعرف أيُّها"):
            _run(school, apply=True)

    def test_a_parent_membership_does_not_count_as_staff(self, school, observer):
        """الموظّفُ الذي هو وليُّ أمرٍ أيضاً ليس ملتبساً: عضويّةُ الكادر واحدة."""
        MembershipFactory(
            user=observer, school=school, role=RoleFactory(school=school, name="parent")
        )
        _run(school, apply=True)
        assert (
            Membership.objects.get(user=observer, role__name="bus_supervisor").job_title
            == "ملاحظ طلبة"
        )

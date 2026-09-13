"""كلماتُ المرور المؤقّتة — قويّةٌ بالبناء، ومؤقّتةٌ بالإلزام، ولا تُخزَّن."""

import pytest
from django.contrib.auth.password_validation import validate_password
from django.core.management import call_command

from core.management.commands.issue_temporary_passwords import LENGTH, make_password
from core.models.audit import AuditLog
from core.models.user import CustomUser
from tests.conftest import MembershipFactory, RoleFactory, UserFactory

pytestmark = pytest.mark.django_db


def _staff(school, name, role_name="teacher", employee=""):
    user = UserFactory(full_name=name)
    if employee:
        user.employee_number = employee
        user.save(update_fields=["employee_number"])
    MembershipFactory(user=user, school=school, role=RoleFactory(school=school, name=role_name))
    return user


def _without_password(school, name, **kw):
    user = _staff(school, name, **kw)
    user.set_unusable_password()
    user.save(update_fields=["password"])
    return user


class TestTheGeneratedPassword:
    """تُرضي المدقّقَ بالبناء لا بالمحاولة — وإلّا دارت الحلقةُ بلا ضمان."""

    @pytest.mark.parametrize("_run", range(40))
    def test_every_generated_password_passes_the_platform_validators(self, _run):
        validate_password(make_password())

    def test_it_has_the_declared_length(self):
        assert len(make_password()) == LENGTH

    def test_it_avoids_the_letters_that_are_misread_off_paper(self):
        """تُقرأ من ورقةٍ وتُكتب بيد — و«O» و«0» بابٌ مغلقٌ على من أخطأ."""
        confusable = set("Ol1I0")

        assert not any(set(make_password()) & confusable for _ in range(60))

    def test_two_calls_do_not_repeat(self):
        assert len({make_password() for _ in range(50)}) == 50


class TestWhoGetsOne:
    def test_only_those_without_a_usable_password(self, db, school, capsys):
        _without_password(school, "بلا كلمة", employee="7001")
        _staff(school, "له كلمة", employee="7002")

        call_command("issue_temporary_passwords")

        out = capsys.readouterr().out
        assert "بلا كلمة" in out
        assert "له كلمة" not in out

    def test_students_and_parents_are_never_included(self, db, school, capsys):
        _without_password(school, "طالب", role_name="student")
        _without_password(school, "وليّ أمر", role_name="parent")
        _without_password(school, "موظّف")

        call_command("issue_temporary_passwords")

        out = capsys.readouterr().out
        assert "موظّف" in out
        assert "طالب" not in out and "وليّ أمر" not in out

    def test_one_person_can_be_singled_out_by_employee_number(self, db, school, capsys):
        _without_password(school, "المقصود", employee="7003")
        _without_password(school, "سواه", employee="7004")

        call_command("issue_temporary_passwords", employee="7003")

        out = capsys.readouterr().out
        assert "المقصود" in out and "سواه" not in out

    def test_nothing_to_do_says_so(self, db, school, capsys):
        _staff(school, "له كلمة")

        call_command("issue_temporary_passwords")

        assert "لا حسابَ بلا كلمة مرور" in capsys.readouterr().out


class TestTheWrite:
    def test_nothing_is_written_without_apply(self, db, school):
        user = _without_password(school, "بلا كلمة")

        call_command("issue_temporary_passwords")

        user.refresh_from_db()
        assert not user.has_usable_password()

    def test_the_password_works_and_the_change_is_forced(self, db, school, capsys):
        user = _without_password(school, "بلا كلمة", employee="7005")

        call_command("issue_temporary_passwords", apply=True)
        printed = [
            line.split()[-1]
            for line in capsys.readouterr().out.splitlines()
            if line.strip().startswith("7005")
        ]

        user.refresh_from_db()
        assert user.has_usable_password()
        assert user.must_change_password is True, "مؤقّتةٌ بالإلزام لا بالنيّة"
        assert user.check_password(printed[0]), "المطبوعةُ هي المكتوبة"

    def test_the_audit_row_names_the_people_and_not_the_passwords(self, db, school, capsys):
        _without_password(school, "بلا كلمة", employee="7006")

        call_command("issue_temporary_passwords", apply=True)
        printed = [
            line.split()[-1]
            for line in capsys.readouterr().out.splitlines()
            if line.strip().startswith("7006")
        ]

        row = AuditLog.objects.filter(changes__event="temporary_passwords_issued").latest(
            "timestamp"
        )
        assert row.changes["people"] == ["بلا كلمة"]
        assert printed[0] not in str(row.changes), "كلمةٌ في سجلٍّ لا يُمحى كلمةٌ مكشوفةٌ أبداً"

    def test_each_person_gets_a_different_password(self, db, school, capsys):
        _without_password(school, "الأوّل", employee="7007")
        _without_password(school, "الثاني", employee="7008")

        call_command("issue_temporary_passwords", apply=True)
        out = capsys.readouterr().out
        first = next(x for x in out.splitlines() if x.strip().startswith("7007")).split()[-1]
        second = next(x for x in out.splitlines() if x.strip().startswith("7008")).split()[-1]

        assert first != second

    def test_running_it_twice_finds_nobody_the_second_time(self, db, school, capsys):
        _without_password(school, "بلا كلمة")

        call_command("issue_temporary_passwords", apply=True)
        capsys.readouterr()
        call_command("issue_temporary_passwords")

        assert "لا حسابَ بلا كلمة مرور" in capsys.readouterr().out

    def test_a_deactivated_account_is_left_alone(self, db, school, capsys):
        """من أُوقف حسابُه لا يُفتح له بابٌ بإصدارِ كلمة."""
        gone = _without_password(school, "موقوف")
        CustomUser.objects.filter(pk=gone.pk).update(is_active=False)

        call_command("issue_temporary_passwords")

        assert "لا حسابَ بلا كلمة مرور" in capsys.readouterr().out

"""[CAPABILITY] القدرةُ المفوَّضة «مُشغِّل الجدول» — منحُها وسحبُها ومصفوفةُ ما تمنح وما لا تمنح.

التذكرة SOS-20260924-1CFE، الجزء أ. الثوابتُ:

    من يمنح ويسحب     المديرُ والنائبُ الأكاديميّ ومطوّرُ المنصّة وحدَهم — لا منسّقٌ ولا نائبٌ إداريّ ولا معلّم
    السببُ إلزاميّ     في المنح والسحب، وكلٌّ منهما في PermissionAuditLog وAuditLog
    لا مسحَ            السحبُ يُعلَّم ولا يُحذف، ومنحٌ فعّالٌ واحدٌ لكلّ (مدرسة، مستخدم، قدرة)
    المصفوفة           المشغِّلُ يسند ويولّد، ولا يعتمد الجدولَ ولا يراجع الأنصبةَ ولا يعتمدها ولا يعتمد التبديل

ولا رقمَ وظيفيّاً ولا اسمَ موظّفٍ حقيقيّاً هنا: كلُّ هويّةٍ مولَّدةٌ لكلّ اختبار.
"""

import uuid
from io import StringIO

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import IntegrityError, transaction

from core import capability_grants as grants
from core import permissions as perms
from core.capabilities import capability, has_capability, registry
from core.models import AuditLog, CapabilityGrant, PermissionAuditLog
from tests.conftest import MembershipFactory, RoleFactory, SchoolFactory, UserFactory

pytestmark = pytest.mark.django_db

KEY = "schedule.operator"
REASON = "تكليفٌ من النائب الإداريّ بمسؤوليّة الجدول العامّ"


def staff(school, role, name="موظّف"):
    user = UserFactory(full_name=name)
    MembershipFactory(user=user, school=school, role=RoleFactory(school=school, name=role))
    return user


def give(school, user, by, reason=REASON):
    return grants.grant(user=user, capability=KEY, by=by, reason=reason)[0]


@pytest.fixture
def principal(school):
    return staff(school, "principal", "المدير")


@pytest.fixture
def teacher(school):
    return staff(school, "teacher", "معلّم")


# ── من يمنح ويسحب ───────────────────────────────────────────────────────────────


@pytest.mark.parametrize("role", ["principal", "vice_academic", "platform_developer"])
def test_the_three_roles_may_grant_and_revoke(school, teacher, role):
    by = staff(school, role, "مانح")

    granted, created = grants.grant(user=teacher, capability=KEY, by=by, reason=REASON)
    assert created and granted.is_active and granted.granted_by == by

    revoked = grants.revoke(user=teacher, capability=KEY, by=by, reason="انتهى التكليف")
    assert revoked is not None and not revoked.is_active and revoked.revoked_by == by


def test_the_platform_developer_by_group_may_grant(school, teacher, developer_user):
    """مطوّرُ المنصّة بمعيار `is_platform_developer` (مجموعة developers) وإن لم يكن دورُه `platform_developer`."""
    assert grants.grant(user=teacher, capability=KEY, by=developer_user, reason=REASON)[1]


@pytest.mark.parametrize(
    "role",
    ["teacher", "coordinator", "vice_admin", "admin_supervisor", "activities_coordinator"],
)
def test_nobody_else_may_grant_or_revoke(school, teacher, principal, role):
    outsider = staff(school, role, "غريب")

    with pytest.raises(grants.GrantError, match="وحدَهم"):
        grants.grant(user=teacher, capability=KEY, by=outsider, reason=REASON)
    give(school, teacher, principal)
    with pytest.raises(grants.GrantError, match="وحدَهم"):
        grants.revoke(user=teacher, capability=KEY, by=outsider, reason="سحبٌ بلا صلاحيّة")

    assert grants.holds(teacher, KEY)  # لم يُسحب


def test_an_anonymous_user_cannot_manage():
    from django.contrib.auth.models import AnonymousUser

    assert not grants.can_manage(AnonymousUser())
    assert not grants.can_manage(None)


def test_a_principal_of_another_school_cannot_grant_here(school, teacher):
    other = staff(SchoolFactory(), "principal", "مديرُ مدرسةٍ أخرى")

    with pytest.raises(grants.GrantError, match="مدرسةٍ أخرى"):
        grants.grant(user=teacher, capability=KEY, by=other, reason=REASON)
    assert not CapabilityGrant.objects.exists()


def test_a_principal_of_another_school_cannot_revoke_here(school, teacher, principal):
    give(school, teacher, principal)
    other = staff(SchoolFactory(), "principal", "مديرُ مدرسةٍ أخرى")

    with pytest.raises(grants.GrantError, match="مدرسةٍ أخرى"):
        grants.revoke(user=teacher, capability=KEY, by=other, reason="سحبٌ من خارج المدرسة")
    assert grants.holds(teacher, KEY)


# ── لمن ─────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("role", ["student", "parent"])
def test_it_is_never_granted_to_a_student_or_a_parent(school, principal, role):
    beneficiary = staff(school, role, "مستفيد")

    with pytest.raises(grants.GrantError, match="لكادرٍ"):
        grants.grant(user=beneficiary, capability=KEY, by=principal, reason=REASON)


def test_it_is_never_granted_to_someone_without_an_active_membership(school, principal):
    stranger = UserFactory(full_name="بلا عضويّة")

    with pytest.raises(grants.GrantError, match="لكادرٍ"):
        grants.grant(user=stranger, capability=KEY, by=principal, reason=REASON)


@pytest.mark.parametrize("capability_key", ["schedule.approve", "schedule.settings", "nope"])
def test_only_a_delegable_capability_can_be_granted(school, teacher, principal, capability_key):
    with pytest.raises(grants.GrantError, match="ليست قدرةً مفوَّضة"):
        grants.grant(user=teacher, capability=capability_key, by=principal, reason=REASON)


# ── السبب ───────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("reason", ["", "   ", "abc", "..", None])
def test_a_grant_and_a_revocation_need_a_reason(school, teacher, principal, reason):
    with pytest.raises(grants.GrantError, match="سببُ المنح"):
        grants.grant(user=teacher, capability=KEY, by=principal, reason=reason)
    give(school, teacher, principal)
    with pytest.raises(grants.GrantError, match="سببُ السحب"):
        grants.revoke(user=teacher, capability=KEY, by=principal, reason=reason)

    assert grants.holds(teacher, KEY)


# ── التدقيق ─────────────────────────────────────────────────────────────────────


def test_a_grant_is_audited_in_both_logs_with_who_whom_when_and_why(school, teacher, principal):
    granted = give(school, teacher, principal)

    trail = PermissionAuditLog.objects.get(action="capability_granted")
    assert (trail.actor, trail.target, trail.school) == (principal, teacher, school)
    assert trail.details == {"capability": KEY, "reason": REASON, "grant": str(granted.pk)}
    assert trail.created_at is not None
    general = AuditLog.objects.get(object_id=str(granted.pk))
    assert general.user == principal and general.action == "create"
    assert general.changes["reason"] == REASON and general.changes["target"] == str(teacher.pk)


def test_a_revocation_is_audited_with_its_own_reason(school, teacher, principal):
    granted = give(school, teacher, principal)

    grants.revoke(user=teacher, capability=KEY, by=principal, reason="عودةُ المنسّق إلى مهامّه")

    trail = PermissionAuditLog.objects.get(action="capability_revoked")
    assert trail.details["reason"] == "عودةُ المنسّق إلى مهامّه" and trail.target == teacher
    assert AuditLog.objects.filter(object_id=str(granted.pk), action="update").count() == 1


def test_granting_twice_changes_and_audits_nothing_more(school, teacher, principal):
    first = give(school, teacher, principal)
    second, created = grants.grant(user=teacher, capability=KEY, by=principal, reason=REASON)

    assert not created and second.pk == first.pk
    assert CapabilityGrant.objects.count() == 1
    assert PermissionAuditLog.objects.filter(action="capability_granted").count() == 1


def test_revoking_what_is_not_held_is_a_quiet_no_op(school, teacher, principal):
    assert grants.revoke(user=teacher, capability=KEY, by=principal, reason="لا منحَ أصلاً") is None
    assert not PermissionAuditLog.objects.filter(action="capability_revoked").exists()


# ── لا مسحَ ────────────────────────────────────────────────────────────────────


def test_a_revoked_grant_stays_as_history_and_a_new_one_can_follow(school, teacher, principal):
    first = give(school, teacher, principal)
    grants.revoke(user=teacher, capability=KEY, by=principal, reason="انتهى التكليف الأوّل")
    second = give(school, teacher, principal, reason="تكليفٌ جديدٌ بعد شهرين")

    assert CapabilityGrant.objects.count() == 2
    first.refresh_from_db()
    assert first.revoked_at is not None and first.revoke_reason == "انتهى التكليف الأوّل"
    assert second.pk != first.pk and second.is_active


def test_the_database_refuses_two_active_grants_of_the_same_capability(school, teacher, principal):
    give(school, teacher, principal)

    with pytest.raises(IntegrityError), transaction.atomic():
        CapabilityGrant.objects.create(
            school=school, user=teacher, capability=KEY, reason=REASON, granted_by=principal
        )


def test_the_database_refuses_a_grant_without_a_reason(school, teacher, principal):
    with pytest.raises(IntegrityError), transaction.atomic():
        CapabilityGrant.objects.create(
            school=school, user=teacher, capability=KEY, reason="", granted_by=principal
        )


def test_the_database_refuses_a_revocation_without_a_reason(school, teacher, principal):
    granted = give(school, teacher, principal)
    granted.revoked_at = granted.created_at

    with pytest.raises(IntegrityError), transaction.atomic():
        granted.save()


# ── القراءة ─────────────────────────────────────────────────────────────────────


def test_holding_follows_the_grant_on_the_same_user_object(school, teacher, principal):
    """يُحفظ الجوابُ على الكائن للطلب — والمنحُ والسحبُ يُبطلانه فلا يبقى قديماً."""
    assert not grants.holds(teacher, KEY)

    give(school, teacher, principal)
    assert grants.holds(teacher, KEY)

    grants.revoke(user=teacher, capability=KEY, by=principal, reason="انتهى التكليف")
    assert not grants.holds(teacher, KEY)


def test_one_query_serves_every_guard_in_the_request(
    school, teacher, principal, django_assert_num_queries
):
    give(school, teacher, principal)
    fresh = type(teacher).objects.get(pk=teacher.pk)

    with django_assert_num_queries(1):
        assert grants.holds(fresh, KEY)
        assert grants.holds(fresh, KEY)
        assert "schedule.operator" in grants.active_keys(fresh)


# ── المصفوفة ────────────────────────────────────────────────────────────────────

#: ما لا يمنحه التفويضُ — كلٌّ منها قدرةٌ مسمّاةٌ في السجلّ.
NOT_GRANTED = [
    "schedule.approve",
    "schedule.settings",
    "workload.review",
    "workload.approve",
    "swap.approve",
    "compensatory.approve",
]


def test_the_operator_assigns_and_generates_but_does_not_approve_or_review(
    school, teacher, principal
):
    give(school, teacher, principal)
    operator = type(teacher).objects.get(pk=teacher.pk)

    assert has_capability(operator, KEY)  # يولّد
    assert has_capability(operator, "workload.edit")  # ويسند
    for key in NOT_GRANTED:
        assert not has_capability(operator, key), key


def test_a_teacher_without_the_grant_holds_neither(school, teacher):
    assert not has_capability(teacher, KEY)
    assert not has_capability(teacher, "workload.edit")


def test_revoking_returns_every_capability(school, teacher, principal):
    give(school, teacher, principal)
    grants.revoke(user=teacher, capability=KEY, by=principal, reason="انتهى التكليف")
    fresh = type(teacher).objects.get(pk=teacher.pk)

    assert not has_capability(fresh, KEY) and not has_capability(fresh, "workload.edit")


def test_the_operator_role_set_is_todays_generators_so_nobody_loses_what_they_have():
    """الأدوارُ في `schedule.operator` هي من يولّد الجدولَ اليوم (`schedule.admin`) — فيربطها الحارسُ دون أن يفقد أحدٌ ما يملك."""
    assert capability(KEY).roles == perms.SCHEDULE_ADMIN
    assert {"principal", "vice_academic"} <= capability(KEY).roles


def test_schedule_approve_is_the_owner_s_three_roles_and_carries_no_grant():
    approve = capability("schedule.approve")

    assert approve.roles == {"principal", "vice_academic", "platform_developer"}
    assert approve.grant is None  # لا يُفوَّض: يُمنح بالدور وحدَه
    assert "vice_admin" not in approve.expanded_roles
    assert "coordinator" not in approve.expanded_roles


@pytest.mark.parametrize("role", ["vice_admin", "coordinator", "teacher"])
def test_nobody_outside_the_three_roles_approves_the_schedule(school, role):
    assert not has_capability(staff(school, role), "schedule.approve")


@pytest.mark.parametrize("role", ["principal", "vice_academic"])
def test_the_principal_and_the_academic_vice_approve_the_schedule(school, role):
    assert has_capability(staff(school, role), "schedule.approve")


def test_both_capabilities_are_in_the_registry_with_a_basis():
    for key in (KEY, "schedule.approve"):
        cap = registry()[key]
        assert cap.label and cap.basis and cap.scope


# ── الأمر الإداريّ ──────────────────────────────────────────────────────────────


def with_number(user):
    user.employee_number = f"T{uuid.uuid4().hex[:9]}"
    user.save(update_fields=["employee_number"])
    return user.employee_number


def run(school, teacher_no, by_no, *extra, reason=REASON):
    out = StringIO()
    call_command(
        "grant_capability",
        "--school", school.code,
        "--employee-number", teacher_no,
        "--by-employee-number", by_no,
        "--reason", reason,
        *extra,
        stdout=out,
    )  # fmt: skip
    return out.getvalue()


def test_the_command_only_previews_without_apply(school, teacher, principal):
    text = run(school, with_number(teacher), with_number(principal))

    assert "عرضٌ فقط" in text and not CapabilityGrant.objects.exists()


def test_the_command_grants_with_apply_and_a_second_run_changes_nothing(school, teacher, principal):
    teacher_no, principal_no = with_number(teacher), with_number(principal)

    run(school, teacher_no, principal_no, "--apply")
    again = run(school, teacher_no, principal_no, "--apply")

    assert CapabilityGrant.objects.filter(revoked_at__isnull=True).count() == 1
    assert "لا تغيير" in again
    assert (
        PermissionAuditLog.objects.filter(action="capability_granted", actor=principal).count() == 1
    )


def test_the_command_revokes_and_lists(school, teacher, principal):
    teacher_no, principal_no = with_number(teacher), with_number(principal)
    run(school, teacher_no, principal_no, "--apply")
    out = StringIO()
    call_command("grant_capability", "--school", school.code, "--list", stdout=out)
    assert "المنحُ الفعّالة" in out.getvalue() and ": 1" in out.getvalue()

    run(school, teacher_no, principal_no, "--revoke", "--apply", reason="انتهى التكليف")

    assert not CapabilityGrant.objects.filter(revoked_at__isnull=True).exists()
    assert CapabilityGrant.objects.get().revoke_reason == "انتهى التكليف"
    nothing = run(school, teacher_no, principal_no, "--revoke", "--apply", reason="مرّةً ثانية")
    assert "لا منحَ فعّالاً" in nothing


@pytest.mark.parametrize("bad", ["<سبب المنح>", "...", "السبب … لاحقاً", "TODO سببٌ"])
def test_the_command_refuses_a_placeholder_reason(school, teacher, principal, bad):
    with pytest.raises(CommandError, match="علامةَ نقص"):
        run(school, with_number(teacher), with_number(principal), "--apply", reason=bad)
    assert not CapabilityGrant.objects.exists()


def test_the_command_refuses_a_granter_who_may_not_grant(school, teacher):
    coordinator = staff(school, "coordinator", "منسّق")

    with pytest.raises(CommandError, match="وحدَهم"):
        run(school, with_number(teacher), with_number(coordinator), "--apply")
    assert not CapabilityGrant.objects.exists()


def test_the_command_refuses_an_unknown_employee(school, principal):
    with pytest.raises(CommandError, match="لا موظّفَ"):
        run(school, "غيرُ موجود", with_number(principal), "--apply")

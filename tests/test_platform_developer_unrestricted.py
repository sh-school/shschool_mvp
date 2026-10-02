"""[SECURITY] مطوّرُ المنصّة لا حظرَ عليه في أيّ صفحة (قرار المالك D-118م، W-20261002-012).

يُلغي D-98م (استبعادُه من `/analytics/`). والقاعدةُ مركزيّة (`core/unrestricted_role.py`) فتشمل كلَّ
قدرةٍ ووحدةٍ، لا قائمةً تُحدَّث صفحةً صفحة. **حقُّ دخولِ صفحةٍ لا نطاقُ بيانات**: عزلُ المدرسة باقٍ.
"""

import pytest
from django.urls import reverse

from core.capabilities import has_capability, registry
from core.models import CustomUser
from core.models.access import Membership, Role
from core.module_registry import _MODULES, gate_admits
from core.navigation import can_open
from core.unrestricted_role import DEVELOPER_EXCLUDED_CAPABILITIES
from tests.test_period_register import (  # noqa: F401 — التجهيزاتُ نفسُها
    _periods,
    kids,
    klass,
    supervisor,
    teacher,
    year,
)

pytestmark = pytest.mark.django_db


@pytest.fixture
def developer(school):
    """حسابٌ بدور المطوّر وحدَه — لا is_superuser ولا مجموعة developers."""
    user = CustomUser.objects.create(
        must_change_password=False, national_id="28700000055", full_name="مطوّر المنصّة"
    )
    user.set_password("Aa!23456789")
    user.save()
    role, _ = Role.objects.get_or_create(school=school, name="platform_developer")
    Membership.objects.create(user=user, school=school, role=role)
    return user


def test_the_developer_holds_every_capability(developer):
    missing = [
        key
        for key in registry()
        if key not in DEVELOPER_EXCLUDED_CAPABILITIES and not has_capability(developer, key)
    ]
    assert not missing, f"قدراتٌ محجوبةٌ عن المطوّر: {missing}"


def test_the_developer_passes_every_module_gate(developer):
    blocked = [
        m.url_prefix
        for m in _MODULES.values()
        if not gate_admits(developer, m.url_prefix, m.allowed_roles)
    ]
    assert not blocked, f"وحداتٌ محجوبةٌ عن المطوّر: {blocked}"


def test_the_developer_can_open_a_guarded_link(developer):
    assert can_open(developer, "analytics_dashboard")


@pytest.mark.parametrize(
    "path",
    ["/analytics/", "/analytics/api/attendance-trend/", "/behavior/committee/", "/reports/"],
)
def test_pages_that_used_to_refuse_the_developer_now_open(client_as, developer, path):
    resp = client_as(developer).get(path)

    assert resp.status_code != 403, path


def test_a_teacher_is_still_refused_the_analytics_pages(client_as, teacher_user):
    """الرفعُ خاصٌّ بالمطوّر — لا يمسّ غيرَه."""
    assert client_as(teacher_user).get("/analytics/").status_code == 403


def test_reverse_of_the_sidebar_link_resolves():
    assert reverse("analytics_dashboard") == "/analytics/"


# ── إسنادُ الدور نفسِه: ترقيةٌ كاملة لا تُمنح من واجهة شؤون الكادر (مراجعة 0105) ──


def _appoint(school, by, role_name="platform_developer", national_id="28700000444"):
    from staff_affairs.appointments import appoint

    return appoint(
        school=school,
        national_id=national_id,
        full_name="مرشَّح",
        role_name=role_name,
        by=by,
        reference="قرار 1",
    )


def test_a_principal_cannot_appoint_the_developer_role(school, principal_user):
    from staff_affairs.appointments import AppointmentError

    with pytest.raises(AppointmentError):
        _appoint(school, principal_user)


def test_a_developer_cannot_appoint_another_developer(school, developer):
    from staff_affairs.appointments import AppointmentError

    with pytest.raises(AppointmentError):
        _appoint(school, developer)


def test_only_a_superuser_can_appoint_the_developer_role(school, django_user_model):
    admin = django_user_model.objects.create(
        national_id="28700000333", full_name="سوبريوزر", is_superuser=True
    )

    membership = _appoint(school, admin)

    assert membership.role.name == "platform_developer"


def test_ordinary_appointments_are_unaffected(school, principal_user):
    membership = _appoint(school, principal_user, role_name="librarian", national_id="28700000555")

    assert membership.role.name == "librarian"


# ── مواضعُ كانت تحجبه بالاسم ضمنيّاً ──


def test_the_developer_sees_the_whole_school_in_student_info(developer):
    from student_info.access import sees_whole_school

    assert sees_whole_school(developer)


def test_the_developer_sees_every_classroom_observation_but_cannot_edit(developer, school):
    from quality.observation_services import ObservationService

    assert ObservationService.visible_to(developer, school).query is not None


def test_reinstating_a_departed_developer_membership_is_also_superuser_only(
    school, principal_user, developer, django_user_model
):
    """مراجعة 0105: إعادةُ عضويّةٍ مُنهاة إسنادٌ من جديد — فلا تفلت من حارس appoint."""
    from staff_affairs.appointments import AppointmentError, reinstate

    membership = developer.memberships.get()
    from django.utils import timezone

    membership.record_departure(
        on=timezone.localdate(), reason="resignation", reference="قرار 9", note=""
    )

    with pytest.raises(AppointmentError):
        reinstate(membership=membership, by=principal_user)

    admin = django_user_model.objects.create(
        national_id="28700000666", full_name="سوبريوزر", is_superuser=True
    )
    assert reinstate(membership=membership, by=admin).is_active


# ── واجهاتُ API أيضاً (قرارُ المالك، أكّده المستخدم) ──


@pytest.mark.parametrize(
    "permission",
    [
        "IsSchoolAdmin",
        "IsLeadership",
        "IsTeacherOrAdmin",
        "IsStaffMember",
        "IsParentOrAdmin",
        "IsSameDepartment",
    ],
)
def test_the_developer_passes_the_api_permission_classes(rf, developer, permission):
    from api import permissions

    request = rf.get("/api/")
    request.user = developer

    assert getattr(permissions, permission)().has_permission(request, view=None)


def test_a_teacher_still_fails_the_leadership_api_permission(rf, teacher_user):
    from api.permissions import IsLeadership

    request = rf.get("/api/")
    request.user = teacher_user

    assert not IsLeadership().has_permission(request, view=None)


def test_the_developer_cannot_read_a_child_through_the_parent_api_without_a_link(
    client_as, developer, school
):
    """مراجعة 0105 (٢): تجاوزُ بوّابة IsParentOrAdmin لا يفتح ملكيّةَ الطالب — الفحصُ الداخليّ باقٍ.

    طالبٌ من مدرسةٍ أخرى بلا ParentStudentLink: يُردّ المطوّرُ عن نقطتَي الأبناء بـ403 لا بقراءة.
    """
    from tests.conftest import MembershipFactory, RoleFactory, SchoolFactory, UserFactory

    other_school = SchoolFactory()
    foreign = UserFactory(full_name="طالب مدرسة أخرى")
    MembershipFactory(
        user=foreign, school=other_school, role=RoleFactory(school=other_school, name="student")
    )
    client = client_as(developer)

    for name in ("api_v1:parent-child-attendance", "api_v1:parent-child-grades"):
        resp = client.get(reverse(name, kwargs={"student_id": foreign.pk}))
        assert resp.status_code in (403, 404), name


# ── سجلُّ التدقيق على دخوله المسارات الحسّاسة: يسجّل ولا يمنع ──


def _audits(user):
    from core.models import AuditLog

    return AuditLog.objects.filter(user=user, changes__via="platform_developer")


def test_a_developer_visit_to_a_sensitive_page_leaves_an_audit_row(client_as, developer):
    resp = client_as(developer).get("/clinic/")

    assert resp.status_code == 200
    row = _audits(developer).get()
    assert row.changes["path"] == "/clinic/" and row.changes["status"] == 200


def test_the_audit_covers_evaluations_and_grievances(client_as, developer):
    client = client_as(developer)
    client.get("/quality/evaluations/")
    client.get("/quality/evaluations/grievances/")

    paths = set(_audits(developer).values_list("changes__path", flat=True))
    assert {"/quality/evaluations/", "/quality/evaluations/grievances/"} <= paths


def test_the_audit_never_blocks_the_developer(client_as, developer):
    assert client_as(developer).get("/clinic/").status_code != 403


def test_other_pages_are_not_audited(client_as, developer):
    client_as(developer).get("/analytics/")

    assert not _audits(developer).exists()


def test_other_roles_are_not_audited_on_the_same_pages(client_as, principal_user):
    client_as(principal_user).get("/clinic/")

    assert not _audits(principal_user).exists()


def test_the_audit_covers_the_student_profile_that_shows_the_health_record(
    client_as, developer, student_user
):
    """مراجعة 0105 على #781: السجلُّ الصحّيّ يظهر في ملفّ الطالب خارج /clinic/ — فيُدقَّق."""
    path = f"/student-affairs/profile/{student_user.pk}/"

    resp = client_as(developer).get(path)

    assert resp.status_code == 200, "التدقيقُ لا يمنع"
    assert _audits(developer).filter(changes__path=path).exists()


@pytest.mark.parametrize(
    "path",
    [
        "/quality/evaluations/approve/00000000-0000-0000-0000-000000000001/",
        "/teacher/smart-schedule/00000000-0000-0000-0000-000000000001/approve/",
    ],
)
def test_a_developer_approval_carries_a_distinct_capacity_mark(rf, developer, path):
    """قرارُ المالك على #781: اعتمادُ الجدول وتقييم الأداء بيد المطوّر بوسمٍ «بصفة مطوّر»."""
    from django.http import HttpResponse

    from core.middleware_developer_audit import DeveloperAccessAuditMiddleware

    request = rf.post(path)
    request.user = developer
    DeveloperAccessAuditMiddleware(lambda r: HttpResponse(status=302))(request)

    row = _audits(developer).get()
    assert row.changes["approval"] is True and row.changes["capacity"] == "بصفة مطوّر"
    assert row.action == "update"


def test_a_plain_get_of_the_approval_url_is_not_marked_as_an_approval(rf, developer):
    from django.http import HttpResponse

    from core.middleware_developer_audit import DeveloperAccessAuditMiddleware

    request = rf.get("/quality/evaluations/approve/00000000-0000-0000-0000-000000000001/")
    request.user = developer
    DeveloperAccessAuditMiddleware(lambda r: HttpResponse(status=200))(request)

    assert "approval" not in _audits(developer).get().changes


# ── استثناءاتُ المالك الصريحة التي لا يفتحها «لا حظرَ»: D-128م (رصدُ الغياب)، D-122م (الزيارة)، المحو ──


@pytest.fixture
def superuser_developer(school, django_user_model):
    """الغالبُ في الإنتاج: حسابُ المطوّر superuser ودورُه platform_developer معاً."""
    user = django_user_model.objects.create(
        must_change_password=False,
        national_id="28700000888",
        full_name="مطوّر-سوبريوزر",
        is_superuser=True,
    )
    user.set_password("Aa!23456789")
    user.save()
    role, _ = Role.objects.get_or_create(school=school, name="platform_developer")
    Membership.objects.create(user=user, school=school, role=role)
    return user


@pytest.mark.parametrize(
    "key", ["attendance.mark", "wings.record_day", "wings.excuse_after_deadline"]
)
def test_the_developer_holds_no_attendance_capability(developer, superuser_developer, key):
    """D-128م: لا يُدخل ولا يعتمد رصدَ غياب الطلبة — بالدور، ولو كان الحسابُ superuser."""
    assert not has_capability(developer, key)
    assert not has_capability(superuser_developer, key)


@pytest.mark.parametrize("view", ["mark_single", "mark_all_present", "mark_late_tap"])
@pytest.mark.parametrize("who", ["developer", "superuser_developer"])
def test_the_developer_cannot_write_attendance(
    request, client_as, school, seeded_calendar, view, who
):
    from django.urls import reverse

    from operations.models import StudentAttendance

    actor = request.getfixturevalue(who)
    klass_ = request.getfixturevalue("klass")
    teacher_ = request.getfixturevalue("teacher")
    (session,) = _periods(school, klass_, teacher_, 1)

    resp = client_as(actor).post(reverse(view, kwargs={"session_id": session.pk}), {})

    assert resp.status_code == 403
    assert not StudentAttendance.objects.filter(session=session).exists()


def test_an_excuse_after_the_deadline_is_refused_to_the_developer(developer, superuser_developer):
    from core.permissions import EXCUSE_AFTER_DEADLINE, WING_DAY_RECORD

    assert "platform_developer" not in EXCUSE_AFTER_DEADLINE | WING_DAY_RECORD


@pytest.mark.parametrize("name", ["erasure-create"])
@pytest.mark.parametrize("who", ["developer", "superuser_developer"])
def test_the_developer_cannot_request_an_erasure(request, client_as, name, who):
    from django.urls import reverse

    actor = request.getfixturevalue(who)

    resp = client_as(actor).post(
        reverse(f"api_v1:{name}"), {"student_id": str(actor.pk), "reason": "x"}, format="json"
    )

    assert resp.status_code == 403


@pytest.mark.parametrize("who", ["developer", "superuser_developer"])
def test_the_developer_cannot_edit_or_archive_an_observation_that_is_not_his(
    request, client_as, school, teacher_user, coordinator_user, who
):
    """D-122م: تعديلُ الزيارة للزائر وحده — ولا أرشفةَ لمن لا يملك الحذف."""
    from django.urls import reverse

    from tests.test_observation_crud import _make_obs

    actor = request.getfixturevalue(who)
    obs, _ = _make_obs(school, coordinator_user, teacher_user, status="draft")
    client = client_as(actor)

    edit = client.post(reverse("observation_edit", kwargs={"obs_id": obs.pk}), {})
    delete = client.post(reverse("observation_delete", kwargs={"obs_id": obs.pk}), {})

    obs.refresh_from_db()
    assert (edit.status_code, delete.status_code) == (403, 403)


def test_every_successful_developer_write_is_marked_with_the_capacity(rf, developer):
    """C2 (0105): وسمٌ عامٌّ لكلّ كتابةٍ ناجحة، على أيّ مسار."""
    from django.http import HttpResponse

    from core.middleware_developer_audit import DeveloperAccessAuditMiddleware

    request = rf.post("/behavior/anything/at/all/")
    request.user = developer
    DeveloperAccessAuditMiddleware(lambda r: HttpResponse(status=302))(request)

    row = _audits(developer).get()
    assert row.changes["capacity"] == "بصفة مطوّر" and row.action == "update"

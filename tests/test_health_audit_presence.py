"""تدقيقُ شاشات العيادة الذاتيّة التحديث بدمج الأسطر (CLN-03، W-20261127-010)."""

import pytest
from django.core.cache import cache
from django.urls import reverse

from core.models import AuditLog
from tests.conftest import ClinicVisitFactory, MembershipFactory, UserFactory
from tests.test_movement_live import _exit, wing_a  # noqa: F401

pytestmark = [pytest.mark.django_db, pytest.mark.pin_clock]

# (المسار، المستخدم): كلُّ شاشةٍ تعرض الخارجين إلى العيادة ويحدّثها المتصفّحُ أو يعيد تحميلها.
SCREENS = [
    ("student_affairs:movements_live", "principal_user"),
    ("student_affairs:student_movements", "principal_user"),
    ("clinic:quick_incoming", "nurse_user"),
    ("clinic:quick_entry", "nurse_user"),
    ("clinic:exit_card", "nurse_user"),
]


@pytest.fixture(autouse=True)
def _clean_cache():
    cache.clear()


def _lines(user):
    """أسطرُ الظهور وحدَها: ما يحمل معرّفاتِ طلبة."""
    lines = AuditLog.objects.filter(user=user, action="view").order_by("timestamp")
    return [line for line in lines if "students" in (line.changes or {})]


@pytest.mark.parametrize(("route", "who"), SCREENS)
def test_ten_refreshes_write_one_line(request, client_as, school, teacher_user, wing_a, route, who):
    user = request.getfixturevalue(who)
    card = _exit(school, wing_a[0], teacher_user, "طالب أول", "29000000011")
    client = client_as(user)

    for _ in range(10):
        assert client.get(reverse(route)).status_code == 200

    (line,) = _lines(user)
    assert line.changes["students"] == [str(card.student_id)]
    assert line.changes["rows"] == 1
    assert card.student.full_name not in f"{line.object_repr} {line.changes}"


@pytest.mark.parametrize(("route", "who"), SCREENS)
def test_new_student_gets_a_line_with_only_that_id(
    request, client_as, school, teacher_user, wing_a, route, who
):
    user = request.getfixturevalue(who)
    _exit(school, wing_a[0], teacher_user, "طالب أول", "29000000011")
    client = client_as(user)
    client.get(reverse(route))

    second = _exit(school, wing_a[0], teacher_user, "طالب ثان", "29000000012")
    client.get(reverse(route))

    lines = _lines(user)
    assert len(lines) == 2
    assert lines[-1].changes["students"] == [str(second.student_id)]


@pytest.mark.parametrize(("route", "who"), SCREENS)
def test_no_clinic_student_no_line(request, client_as, school, teacher_user, wing_a, route, who):
    user = request.getfixturevalue(who)
    _exit(school, wing_a[0], teacher_user, "طالب دورة", "29000000011", dest="restroom")
    _exit(school, wing_a[0], teacher_user, "طالب قادم", "29000000012", dest="wing_sup")

    assert client_as(user).get(reverse(route)).status_code == 200

    assert _lines(user) == []


def test_lost_cache_repeats_the_line(client_as, school, principal_user, teacher_user, wing_a):
    _exit(school, wing_a[0], teacher_user, "طالب أول", "29000000011")
    client = client_as(principal_user)
    url = reverse("student_affairs:movements_live")

    client.get(url)
    cache.clear()
    client.get(url)

    assert len(_lines(principal_user)) == 2


# قائمةُ الزيارات والطابور (قرار 2026-11-27): الدمجُ بالطالب لا بالدقيقة، فالجديدُ يُسجَّل فوراً.
QUEUE_VIEWS = ["clinic:visits_list", "clinic:quick_queue", "clinic:quick_entry"]


def _late_student(school, role, nurse_user):
    """زيارةٌ اليوم لطالبٍ جديدٍ يظهر بعد أوّل فتح، بعضويّة طالب الاختبار نفسها."""
    late = UserFactory(full_name="طالب متأخّر")
    MembershipFactory(user=late, school=school, role=role)
    ClinicVisitFactory(school=school, student=late, nurse=nurse_user)
    return late


@pytest.mark.parametrize("route", QUEUE_VIEWS)
def test_student_appearing_within_the_same_minute_gets_own_line(
    client_as, school, nurse_user, student_user, clinic_visit, route
):
    client = client_as(nurse_user)
    assert client.get(reverse(route)).status_code == 200
    role = student_user.memberships.get().role
    late = _late_student(school, role, nurse_user)

    assert client.get(reverse(route)).status_code == 200
    assert client.get(reverse(route)).status_code == 200  # إعادةُ التحديث لا تكرّر

    lines = _lines(nurse_user)
    assert len(lines) == 2
    assert lines[0].changes["students"] == [str(student_user.pk)]
    assert lines[1].changes["students"] == [str(late.pk)]
    assert late.full_name not in f"{lines[1].object_repr} {lines[1].changes}"


def test_visits_search_with_no_match_writes_no_line(client_as, nurse_user, clinic_visit):
    """لا طالبَ ظاهراً = لا سطر، ومصطلحُ البحث لا يدخل السطر."""
    client = client_as(nurse_user)
    response = client.get(reverse("clinic:visits_list"), {"student": "اسمٌ لا مطابق"})
    assert response.status_code == 200
    assert _lines(nurse_user) == []

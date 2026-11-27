"""تدقيقُ ظهور العيادة في الشاشات اليدويّة (بالدمج اليوميّ) وفي التصدير (بلا دمج) — CLN-03، W-20261127-011."""

import datetime as dt

import pytest
from django.core.cache import cache
from django.http import QueryDict
from django.urls import reverse

from core.exports import registry
from core.models import AuditLog
from operations.class_exit import change_destination
from operations.models import ClassExit
from tests.attendance_fixtures import *  # noqa: F401,F403
from tests.conftest import StudentEnrollmentFactory, UserFactory
from tests.test_class_grid import (  # noqa: F401
    _exit as _grid_exit,
)
from tests.test_class_grid import _grid_on, assigned, clock, kids, subject  # noqa: F401
from tests.test_movement_live import _exit, wing_a  # noqa: F401
from tests.test_period_register import SUNDAY, _confirm, _periods

pytestmark = [pytest.mark.django_db, pytest.mark.pin_clock]


@pytest.fixture(autouse=True)
def _clean_cache():
    cache.clear()


def _presence(user, screen):
    lines = AuditLog.objects.filter(user=user, action="view").order_by("timestamp")
    return [line.changes for line in lines if (line.changes or {}).get("screen") == screen]


def _assert_one_line(user, screen, student_id):
    assert _presence(user, screen) == [{"screen": screen, "rows": 1, "students": [str(student_id)]}]


# ── جدولُ رصد المعلّم ──────────────────────────────────────────────────────────


@pytest.mark.parametrize("returned", [False, True])
def test_class_grid_logs_clinic_once(
    client_as, assigned, teacher, principal_user, kids, clock, returned
):
    clock(7, 30)
    client = client_as(teacher)
    # المعلّمُ يُخرج إلى مشرف الجناح وحدَه، ووجهةُ العيادة يحدّدها غيرُه.
    _grid_exit(client, assigned, kids[0], action="leave", destination="wing_sup")
    change_destination(ClassExit.objects.get(), "clinic", principal_user)
    if returned:
        _grid_exit(client, assigned, kids[0], action="return")
        clock(9, 0)  # لا حصّةَ جارية: يبقى التلميحُ وحدَه
    url = reverse("class_grid", args=[assigned.id])

    for _ in range(3):
        assert client.get(url).status_code == 200

    _assert_one_line(teacher, "جدول رصد المعلم", kids[0].pk)


def test_class_grid_without_clinic_logs_nothing(client_as, assigned, teacher, kids, clock):
    clock(7, 30)
    client = client_as(teacher)
    _grid_exit(client, assigned, kids[0], action="leave", destination="wing_sup")

    assert client.get(reverse("class_grid", args=[assigned.id])).status_code == 200

    assert _presence(teacher, "جدول رصد المعلم") == []


# ── جدولُ سجلّ اليوم والسجلُّ التاريخيّ ────────────────────────────────────────

LOGS = [
    ("student_affairs:student_movements", "سجل خروج اليوم"),
    ("student_affairs:movements_history", "سجل الخروج التاريخي"),
]


@pytest.mark.parametrize(("route", "screen"), LOGS)
def test_movement_logs_record_clinic_once(
    client_as, school, principal_user, teacher_user, wing_a, route, screen
):
    card = _exit(school, wing_a[0], teacher_user, "طالب أول", "29000000011", back_after=2)
    client = client_as(principal_user)

    for _ in range(3):
        assert client.get(reverse(route)).status_code == 200

    _assert_one_line(principal_user, screen, card.student_id)


@pytest.mark.parametrize(("route", "screen"), LOGS)
def test_movement_logs_without_clinic_log_nothing(
    client_as, school, principal_user, teacher_user, wing_a, route, screen
):
    _exit(school, wing_a[0], teacher_user, "طالب أول", "29000000011", dest="restroom", back_after=2)

    assert client_as(principal_user).get(reverse(route)).status_code == 200

    assert _presence(principal_user, screen) == []


# ── صفحةُ أحداث الطالب ─────────────────────────────────────────────────────────


@pytest.mark.parametrize(("dest", "expected"), [("clinic", 1), ("restroom", 0)])
def test_student_events_exit(
    client_as, school, principal_user, teacher_user, wing_a, dest, expected
):
    card = _exit(school, wing_a[0], teacher_user, "طالب أول", "29000000011", dest=dest)
    client = client_as(principal_user)
    url = reverse("wings:student_events", args=[wing_a[0].id, card.student_id])

    for _ in range(3):
        assert client.get(url).status_code == 200

    assert len(_presence(principal_user, "سجل أحداث الطالب")) == expected


def _marked(school, klass, teacher, marker, where):
    """طالبٌ غائبٌ بمكانٍ معلومٍ في حصّةٍ واحدةٍ يومَ الأحد."""
    student = UserFactory(full_name="طالب أول", national_id="29000000011")
    StudentEnrollmentFactory(
        student=student, class_group=klass, enrolled_at=SUNDAY - dt.timedelta(days=30)
    )
    (period,) = _periods(school, klass, teacher, 1)
    _confirm(klass, period, {student: {"status": "absent", "whereabouts": where}}, marker)
    return student


@pytest.mark.parametrize(("where", "expected"), [("clinic", 1), ("activity", 0)])
def test_student_events_whereabouts(
    client_as, school, principal_user, teacher_user, wing_a, where, expected
):
    student = _marked(school, wing_a[0], teacher_user, principal_user, where)
    url = reverse("wings:student_events", args=[wing_a[0].id, student.id])

    assert client_as(principal_user).get(url).status_code == 200

    assert len(_presence(principal_user, "سجل أحداث الطالب")) == expected


# ── التصدير ───────────────────────────────────────────────────────────────────


def _export_lines(user):
    lines = AuditLog.objects.filter(user=user, action="view", model_name__in=["Wing", "ClassGroup"])
    return list(lines)


@pytest.mark.parametrize(("where", "expected"), [("clinic", 2), ("activity", 0)])
@pytest.mark.parametrize("scope", ["section", "wing"])
def test_register_file_logs_every_issue(
    client_as, school, principal_user, teacher_user, wing_a, scope, where, expected
):
    klass = wing_a[0]
    student = _marked(school, klass, teacher_user, principal_user, where)
    if scope == "section":
        url, record = reverse("wings:section_register", args=[klass.id]), klass
    else:
        url, record = reverse("wings:wing_register", args=[klass.wing.code]), klass.wing
    client = client_as(principal_user)

    for _ in range(2):
        response = client.get(f"{url}?date={SUNDAY.isoformat()}&format=xlsx")
        assert response.status_code == 200

    lines = _export_lines(principal_user)
    assert len(lines) == expected
    for line in lines:
        assert line.object_id == str(record.pk)
        assert line.changes["rows"] == 1
        assert student.full_name not in f"{line.object_repr} {line.changes}"


@pytest.mark.parametrize(
    ("where", "query", "expected"),
    [("clinic", "", 2), ("activity", "", 0), ("clinic", "&hide=marks", 0)],
)
def test_register_table_export_logs_every_build(
    school, principal_user, teacher_user, wing_a, where, query, expected
):
    klass = wing_a[0]
    _marked(school, klass, teacher_user, principal_user, where)
    params = QueryDict(f"date={SUNDAY.isoformat()}&wing={klass.wing.code}{query}")

    for _ in range(2):
        registry.get("wings.register_xlsx").build(school, principal_user, params)

    lines = _export_lines(principal_user)
    assert len(lines) == expected
    assert all(line.object_id == str(klass.wing.pk) for line in lines)
    assert all(line.changes["rows"] == 1 for line in lines)

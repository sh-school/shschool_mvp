"""[SECURITY] النائبُ الأكاديميّ يراقب الغيابَ ولا يرصده (المرحلة أ٤؛ D-201م وD-239م؛ W-20261004-024).

كان في `WING_DAY_RECORD`، فتفتح له `wings.record_day` شاشاتِ الرصد في الأجنحة الخمسة (`wings_of` تعطي القيادةَ كلَّها):
قبولُ العذر وإلغاؤه، وسجلُّ الاتّصال، وحذفُ أحداث الحضور، وملفُّ الغياب. فخرج منها؛ ويبقى يرى إحصائياتِ الغياب
(`student_affairs.follow_up`) وغيابَ اليوم وجدولَ الشعبة قارئاً (`GRID_READER` — يحرسه tests/test_class_grid.py)،
وصار يصله تنبيهُ العتبة مع الأخصائيّ (`ABSENCE_ALERT_RECIPIENTS`). وجدولُ الأدوار في
docs/attendance_roles_phase_a.md يطابق الشيفرةَ بآخر اختبارٍ هنا.
"""

import re
from datetime import timedelta
from pathlib import Path

import pytest
from django.urls import reverse

from core import permissions
from core.capabilities import has_capability
from core.navigation import can_open
from operations.attendance_policy import GRID_WRITER_ROLES
from operations.day_attendance import is_recorder
from operations.models import AbsenceExcuse
from operations.services import AttendanceService
from tests.attendance_fixtures import *  # noqa: F401,F403
from tests.attendance_fixtures import _staff
from tests.test_absence_alerts import _absent, student, subject, year_window  # noqa: F401

pytestmark = pytest.mark.django_db

ROLES_TABLE = Path(__file__).resolve().parent.parent / "docs" / "attendance_roles_phase_a.md"

#: أعمدةُ جدول الأدوار ومجموعاتُها في الشيفرة — الجدولُ يُقرأ بها فلا يتباعدان.
TABLE_COLUMNS = {
    "رصد يوم الجناح": permissions.WING_DAY_RECORD,
    "كتابة الجدول بالدور": GRID_WRITER_ROLES,
    "متابعة الغياب": permissions.STUDENT_FOLLOW_UP,
    "تنبيه العتبة": permissions.ABSENCE_ALERT_RECIPIENTS,
    "عذر بعد المهلة": permissions.EXCUSE_AFTER_DEADLINE,
}


@pytest.fixture
def deputy(school):
    return _staff(school, "vice_academic", "النائب الأكاديميّ", "29000000211")


# ── لا يرصد ولا يعتمد ──


def test_the_deputy_left_the_wing_record_group_and_it_now_equals_the_grid_writers():
    """المجموعتان تقولان «من يكتب الغياب» في موضعين؛ وبخروج النائب تطابقتا — فلا تفترقان صامتتين."""
    assert "vice_academic" not in permissions.WING_DAY_RECORD
    assert permissions.WING_DAY_RECORD == GRID_WRITER_ROLES


def test_the_deputy_neither_holds_the_record_capability_nor_is_a_recorder(deputy):
    assert not has_capability(deputy, "wings.record_day")
    assert not can_open(deputy, "wings:record_index"), "لا رابطَ رصدٍ يُعرض له"
    assert is_recorder(deputy) is False


@pytest.mark.parametrize(
    ("name", "args"),
    [
        ("wings:record_index", lambda klass, kid: []),
        ("wings:record_section", lambda klass, kid: [klass.id]),
        ("wings:student_events", lambda klass, kid: [klass.id, kid.id]),
        ("wings:absence_file", lambda klass, kid: [kid.id]),
    ],
)
def test_the_deputy_is_refused_the_record_screens(client_as, deputy, klass, kid, name, args):
    response = client_as(deputy).get(reverse(name, args=args(klass, kid)))
    assert response.status_code in (302, 403)


@pytest.mark.parametrize(
    ("name", "args"),
    [
        ("wings:excuse_grant", lambda klass, kid: [klass.id, kid.id]),
        ("wings:guardian_contact_log", lambda klass, kid: [klass.id, kid.id]),
        ("wings:absence_file_excuse", lambda klass, kid: [kid.id]),
    ],
)
def test_the_deputy_cannot_accept_an_excuse_or_log_a_contact(
    client_as, deputy, klass, kid, name, args
):
    response = client_as(deputy).post(reverse(name, args=args(klass, kid)), {"note": "عذر"})
    assert response.status_code in (302, 403)
    assert not AbsenceExcuse.objects.exists()


# ── ويرى ──


def test_the_deputy_still_sees_the_absence_statistics_without_a_dead_record_button(
    client_as, deputy
):
    """«إحصائيات الغياب» كانت تعرض زرَّ «رصد الغياب» لكلّ داخلٍ — فيصير للنائب رابطاً إلى 403."""
    response = client_as(deputy).get(reverse("student_affairs:attendance_overview"))
    assert response.status_code == 200
    assert reverse("wings:record_index") not in response.content.decode()


def test_the_deputy_still_sees_todays_absence(client_as, deputy):
    assert has_capability(deputy, "operations.daily_absence")
    assert client_as(deputy).get(reverse("daily_report")).status_code == 200


# ── وصله التنبيه ──


def test_the_threshold_alert_reaches_the_deputy_and_the_social_worker_only(
    school, class_group, teacher_user, subject, student, year_window, deputy
):
    from notifications.models import InAppNotification

    worker = _staff(school, "social_worker", "الأخصائيّ", "29000000221")
    _staff(school, "vice_admin", "النائب الإداريّ", "29000000231")
    _staff(school, "admin_supervisor", "المشرف", "29000000241")
    start, _ = year_window
    _absent(school, class_group, teacher_user, subject, student, start, 3)

    AttendanceService.raise_absence_alerts(student, school, on=start + timedelta(days=3))

    notified = set(
        InAppNotification.objects.filter(event_type="absence").values_list("user_id", flat=True)
    )
    assert notified == {deputy.id, worker.id}


def test_each_recipient_gets_one_notice_per_gate(
    school, class_group, teacher_user, subject, student, year_window, deputy
):
    from notifications.models import InAppNotification

    start, _ = year_window
    _absent(school, class_group, teacher_user, subject, student, start, 3)
    day = start + timedelta(days=3)

    AttendanceService.raise_absence_alerts(student, school, on=day)
    AttendanceService.raise_absence_alerts(student, school, on=day)

    assert InAppNotification.objects.filter(user=deputy, event_type="absence").count() == 1


# ── ولا يتأثّر غيرُه ──


@pytest.mark.parametrize(
    "role", ["student_affairs_coordinator", "vice_admin", "principal", "admin_supervisor"]
)
def test_the_other_recorders_keep_recording(school, role):
    user = _staff(school, role, role, "29000000250")
    assert has_capability(user, "wings.record_day")
    assert is_recorder(user) is True


# ── جدولُ الأدوار في docs يطابق الشيفرة ──


def _table() -> tuple[list[str], dict[str, list[str]]]:
    text = ROLES_TABLE.read_text(encoding="utf-8")
    block = text.split("<!-- roles-table:start -->", 1)[1].split("<!-- roles-table:end -->", 1)[0]
    rows = [
        [cell.strip() for cell in line.strip().strip("|").split("|")]
        for line in block.splitlines()
        if line.strip().startswith("|")
    ]
    header, body = rows[0], rows[2:]
    return header, {re.sub(r"`", "", row[1]): row for row in body}


def test_the_roles_table_in_docs_matches_the_code():
    header, rows = _table()
    for column, roles in TABLE_COLUMNS.items():
        index = header.index(column)
        marked = {role for role, row in rows.items() if row[index] == "نعم"}
        assert marked == set(roles), f"عمود «{column}» يخالف الشيفرة"
    assert rows["vice_academic"][header.index("رصد يوم الجناح")] == "لا"

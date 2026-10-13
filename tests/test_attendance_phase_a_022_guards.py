"""حرّاسُ المرحلة أ٢ من آليّة الغياب (W-20261004-022، D-201م): ثغراتُ صلاحيّات الرصد.

الاستقصاءُ على main (b2e4d578): من الدوالّ الأربع في المواصفة لم يبقَ إلّا `tardiness_record`. وحذفُ الثلاث الأخرى
(`complete_session` و`session_summary` و`bulk_mark_all_present`) في 0a7c3a5f2 (#913، W-20261009-003، «حذف الشبكة القديمة
وكلّ كود الاعتماد») — فلا ثغرةَ تُسدّ في دالّةٍ غيرِ موجودة؛ ورصدُ الحصّة كلُّه اليومَ من جدول الشعبة (`can_write_grid`).

وثغرةُ `tardiness_record` كانت ثلاثاً، وكلٌّ هنا باختبار:
- تكتب فوق أيّ رصدٍ قائم (غيابٌ رصده المعلّمُ أو رصدُ مشرفٍ ينقلب «متأخّراً» بنقرة، بلا سجلّ).
- تأخذ «أوّلَ حصّةٍ» لا الحصّةَ الجارية — وللقيادة «أوّلَ حصّةٍ في المدرسة»: شعبةٌ ليست شعبتَه
  (`test_supervisor_student_affairs_followup.py::test_leadership_has_no_school_fallback_any_more`).
- لا تسأل من يكتب جدولَ الشعبة: فالنائبُ الأكاديميّ — وهو يراقب ولا يرصد (D-201م ١) — كان يرصد التأخّر.
"""

import ast
from pathlib import Path

import pytest
from django.contrib.messages import get_messages
from django.urls import reverse

from core import permissions
from core.capabilities import capability
from core.models import AuditLog
from core.permissions import expand_roles
from operations.models import ClassExit, Session, StudentAttendance, SubjectClassAssignment
from operations.models.attendance_ledger import AttendanceEntry
from student_affairs import morning_tardiness
from tests.attendance_fixtures import *  # noqa: F401,F403
from tests.attendance_fixtures import SUNDAY, _staff
from tests.conftest import ClassGroupFactory
from tests.test_class_grid import (  # noqa: F401 — التجهيزاتُ نفسُها
    _cells,
    _grid_on,
    _save,
    assigned,
    clock,
    kids,
    subject,
)

pytestmark = pytest.mark.django_db

ROOT = Path(__file__).resolve().parents[1]


def _morning(client, student):
    return client.post(reverse("student_affairs:tardiness_record"), {"student_id": str(student.pk)})


def _said(response) -> str:
    return " ".join(str(m) for m in get_messages(response.wsgi_request))


def _open_period(client_as, teacher, assigned, kids, clock, number, hour, minute):
    """المعلّمُ يرصد طالباً آخرَ في ح`number` فتُنشأ حصّتُها كما في الواقع — والطالبُ المتأخّرُ بلا رصد."""
    clock(hour, minute)
    assert (
        _save(client_as(teacher), assigned, number, [_cells(kids[1], "present")]).status_code == 200
    )
    return Session.objects.get(class_group=assigned, date=SUNDAY, period_number=number)


def _row(student):
    return StudentAttendance.objects.filter(student=student).values(
        "session_id", "status", "source", "tardiness_recorded_at"
    )


def _tardiness_trails():
    return AuditLog.objects.filter(action="create", object_repr__startswith="تسجيل تأخير").count()


class TestAnExistingMarkIsNeverOverwritten:
    def test_the_teachers_absent_is_not_turned_late(
        self, client_as, assigned, teacher, holder, kid, kids, clock
    ):
        _open_period(client_as, teacher, assigned, kids, clock, 1, 7, 30)
        _save(client_as(teacher), assigned, 1, [_cells(kid, "absent")])
        before = list(_row(kid))
        assert before[0]["status"] == "absent"

        response = _morning(client_as(holder), kid)

        assert response.status_code == 302
        assert list(_row(kid)) == before
        assert "يُصحَّح الرصدُ من جدول الشعبة" in _said(response)
        assert _tardiness_trails() == 0

    def test_a_supervisors_mark_is_not_overwritten(
        self, client_as, assigned, teacher, holder, kid, kids, clock, school
    ):
        first = _open_period(client_as, teacher, assigned, kids, clock, 1, 7, 30)
        StudentAttendance.objects.create(
            school=school, session=first, student=kid, status="present", source="supervisor"
        )
        before = list(_row(kid))

        _morning(client_as(holder), kid)

        assert list(_row(kid)) == before

    def test_an_entry_alone_still_blocks(
        self, client_as, assigned, teacher, holder, kid, kids, clock
    ):
        """إدخالُ المعلّم في السجلّ رصدٌ ولو غاب صفُّه المعتمَد — لا يُكتب بجواره تأخّرٌ يناقضه."""
        _open_period(client_as, teacher, assigned, kids, clock, 1, 7, 30)
        _save(client_as(teacher), assigned, 1, [_cells(kid, "absent")])
        StudentAttendance.objects.filter(student=kid).delete()
        assert AttendanceEntry.objects.filter(student=kid).exists()

        _morning(client_as(holder), kid)

        assert not StudentAttendance.objects.filter(student=kid).exists()

    def test_a_row_written_in_the_same_instant_is_a_refusal_not_a_500(
        self, client_as, assigned, teacher, holder, kid, kids, clock, school, monkeypatch
    ):
        first = _open_period(client_as, teacher, assigned, kids, clock, 1, 7, 30)
        StudentAttendance.objects.create(
            school=school, session=first, student=kid, status="absent", source="teacher"
        )
        # الفحصُ المسبق رأى «لا رصد» ثمّ كتب غيرُه قبل الإنشاء: القيدُ الفريدُ هو الحَكَم.
        monkeypatch.setattr(morning_tardiness, "_already_marked", lambda *_: False)

        response = _morning(client_as(holder), kid)

        assert response.status_code == 302
        assert [r["status"] for r in _row(kid)] == ["absent"]
        assert _tardiness_trails() == 0


class TestItLandsOnHisCurrentPeriod:
    def test_the_period_running_now_not_the_first_of_the_day(
        self, client_as, assigned, teacher, holder, kid, kids, clock
    ):
        _open_period(client_as, teacher, assigned, kids, clock, 1, 7, 30)
        second = _open_period(client_as, teacher, assigned, kids, clock, 2, 8, 10)
        clock(8, 20)

        _morning(client_as(holder), kid)

        (row,) = _row(kid)
        assert (row["session_id"], row["status"], row["source"]) == (
            second.id,
            "late",
            "supervisor",
        )
        assert row["tardiness_recorded_at"] is not None

    def test_no_running_period_means_no_record(
        self, client_as, assigned, teacher, holder, kid, kids, clock
    ):
        _open_period(client_as, teacher, assigned, kids, clock, 1, 7, 30)
        _open_period(client_as, teacher, assigned, kids, clock, 2, 8, 10)
        clock(9, 0)  # بعد ح2 (08:45) وقبل ح3 (12:45)

        response = _morning(client_as(holder), kid)

        assert not _row(kid).exists()
        assert "لا حصّةَ جاريةً الآن" in _said(response)


class TestWhoRecordsIsWhoWritesTheGrid:
    def test_the_wing_holder_records_at_the_gate(
        self, client_as, assigned, teacher, holder, kid, kids, clock
    ):
        first = _open_period(client_as, teacher, assigned, kids, clock, 1, 7, 30)

        _morning(client_as(holder), kid)

        (row,) = _row(kid)
        assert (row["session_id"], row["status"]) == (first.id, "late")
        assert _tardiness_trails() == 1

    def test_the_academic_vice_watches_and_does_not_record(
        self, client_as, assigned, teacher, kid, kids, clock, school
    ):
        """يحمل `student_affairs.tardiness` بقيادة شؤون الطلبة، ولا يكتب جدولَ الشعبة (D-201م ١، D-239م ١)."""
        vice = _staff(school, "vice_academic", "النائب الأكاديمي", "29000001030")
        _open_period(client_as, teacher, assigned, kids, clock, 1, 7, 30)

        response = _morning(client_as(vice), kid)

        assert response.status_code == 302
        assert not _row(kid).exists()
        assert "لا الرصدُ فيه" in _said(response)


# ── كلُّ نقطة كتابةٍ في جدول الشعبة: من ليس معلّمَها ولا حاملَ جناحها ولا قيادتَها ← 404 بلا أثر ─────────────

#: أدوارٌ تعليميّةٌ تحمل `attendance.mark` بنفسها أو بالوراثة — وكلٌّ هنا مُسنَدٌ إلى شعبةٍ أخرى لا إلى هذه.
#: والتربيةُ الخاصّةُ ومساعدوها منهم: لا مسارَ لهم يتجاوز الإدخالَ والقرار (`write_grid_cell`).
OUTSIDERS = (
    "teacher",
    "ese_teacher",
    "coordinator",
    "teacher_assistant",
    "ese_assistant",
    "e_projects_coordinator",
)


@pytest.fixture
def outsider(school, year, subject, assigned, request):
    role = request.param
    user = _staff(school, role, f"دورٌ خارج الشعبة {role}", f"2900000105{OUTSIDERS.index(role)}")
    elsewhere = ClassGroupFactory(
        school=school, grade="G8", section="2", level_type="prep", academic_year=year
    )
    SubjectClassAssignment.objects.create(
        school=school,
        class_group=elsewhere,
        subject=subject,
        teacher=user,
        weekly_periods=2,
        academic_year=year,
    )
    return user


def _written():
    return (
        AttendanceEntry.objects.count(),
        StudentAttendance.objects.count(),
        ClassExit.objects.count(),
    )


@pytest.mark.parametrize("outsider", OUTSIDERS, indirect=True)
def test_every_grid_write_point_is_404_for_whoever_does_not_teach_the_class(
    client_as, assigned, outsider, kid, clock
):
    clock(7, 30)
    client = client_as(outsider)
    before = _written()
    student = {"student": str(kid.pk)}

    responses = {
        "save": _save(client, assigned, 1, [_cells(kid, "absent")]),
        "late": client.post(reverse("class_grid_late", args=[assigned.id]), student),
        "exit": client.post(
            reverse("class_grid_exit", args=[assigned.id]), {**student, "action": "leave"}
        ),
    }

    assert {name: r.status_code for name, r in responses.items()} == dict.fromkeys(responses, 404)
    assert _written() == before


# ── قدراتُ الرصد: لكلٍّ مصدرٌ واحدٌ في core/permissions.py — والحارسُ يسقط على قائمةٍ ثانية ───────────

#: قدرةٌ تحكم رصدَ الغياب أو التأخّر ← الثابتُ الوحيدُ الذي تُعرَّف به. قدرةٌ جديدةٌ للرصد تُضاف هنا بثابتها.
SINGLE_SOURCE = {
    "attendance.mark": "ATTENDANCE_RECORD",
    "wings.record_day": "WING_DAY_RECORD",
    "student_affairs.tardiness": "STUDENT_FOLLOW_UP",
}


def _cap_roles_argument(key: str) -> str:
    tree = ast.parse((ROOT / "core/capabilities.py").read_text(encoding="utf-8"))
    found = [
        node.args[2]
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and getattr(node.func, "id", "") == "_cap"
        and len(node.args) >= 3
        and isinstance(node.args[0], ast.Constant)
        and node.args[0].value == key
    ]
    assert len(found) == 1, f"{key}: لا تعريفَ واحداً في core/capabilities.py"
    return ast.unparse(found[0])


def _assignments_of(name: str) -> list[str]:
    """كلُّ ملفٍّ إنتاجيٍّ يُسنِد إلى `name` على مستوى الوحدة — المصدرُ الواحدُ ملفٌّ واحد."""
    skipped = {"tests", "migrations", "node_modules", "staticfiles"}
    where = []
    for path in ROOT.rglob("*.py"):
        parts = path.relative_to(ROOT).parts
        if any(part.startswith(".") or part in skipped for part in parts):
            continue
        text = path.read_text(encoding="utf-8")
        if name not in text:
            continue
        for node in ast.parse(text).body:
            targets = node.targets if isinstance(node, ast.Assign) else []
            if isinstance(node, ast.AnnAssign):
                targets = [node.target]
            if any(isinstance(t, ast.Name) and t.id == name for t in targets):
                where.append(path.relative_to(ROOT).as_posix())
    return where


@pytest.mark.parametrize("key", sorted(SINGLE_SOURCE))
def test_each_marking_capability_points_at_its_one_role_group(key):
    name = SINGLE_SOURCE[key]

    hint = f"{key} تُعرِّف أدوارَها بنفسها — قائمةٌ ثانية؛ اجعلها P.{name}"
    assert _cap_roles_argument(key) == f"P.{name}", hint
    assert _assignments_of(name) == ["core/permissions.py"]
    assert isinstance(getattr(permissions, name), frozenset)
    assert capability(key).roles == getattr(permissions, name)


def test_unifying_the_lists_kept_who_holds_the_marking_capability():
    """التوحيدُ لا يغيّر من يحمل القدرة بعد الوراثة: هم من كانوا يحملونها حين كانت قائمةً حرفيّة في السجلّ."""
    before = {
        "principal",
        "vice_academic",
        "vice_admin",
        "coordinator",
        "teacher",
        "ese_teacher",
        "admin_supervisor",
    }

    assert capability("attendance.mark").expanded_roles == frozenset(expand_roles(before))
    assert "activities_coordinator" not in permissions.ATTENDANCE_RECORD

"""[LEGAL] `mark_single` لا يكتب حصّةَ غيرِ معلّمها — ثغرةٌ حيّةٌ في شُعب التربية الخاصّة (W-20261002-026، حكمُ 0105 N1).

كان `mark_single` يفحص «أيرصد هذا الدورُ في هذه الشعبة؟» (`can_record`) ولا يفحص «أهو معلّمُ هذه الحصّة؟».
وشُعبُ بلا جناحٍ (ثلاثُ شُعب ESE) يرصدها كلُّ معلّمٍ يحمل `attendance.mark` — فمعلّمٌ يكتب حضورَ حصّةِ زميله
بتبديل `session_id`، ولا نافذةَ زمنٍ تمنعه. وهذا كسرُ وصولٍ أفقيٌّ على سند خصمٍ وتأديب.

الإصلاحُ: غيرُ أهل الرصد (`is_recorder`) لا يكتب إلّا **معلّمُ الحصّة الفعليّ** داخل نافذتها
(`attendance_policy.can_enter`: عضويّةٌ في المدرسة، معلّمُ الحصّة، ليست ملغاة، قيدُ الطالب بتاريخها، ومن بدء
الحصّة حتى نهاية الدوام بتوقيت الدوحة). أمّا أهلُ الرصد (المشرفُ والنائبان والمدير) فكما كانوا.
"""

import datetime as dt

import pytest
from django.urls import reverse
from django.utils import timezone

from core.academic_calendar import academic_year_for_school
from operations.models import Session, StudentAttendance
from tests.conftest import (
    ClassGroupFactory,
    MembershipFactory,
    RoleFactory,
    StudentEnrollmentFactory,
    UserFactory,
)

pytestmark = pytest.mark.django_db

SUNDAY = dt.date(2026, 9, 13)
ENROLLED = dt.date(2026, 9, 1)


def at(hour, minute, second=0, day=SUNDAY):
    return timezone.make_aware(dt.datetime.combine(day, dt.time(hour, minute, second)))


def _staff(school, role, name, national_id):
    user = UserFactory(full_name=name, national_id=national_id)
    MembershipFactory(user=user, school=school, role=RoleFactory(school=school, name=role))
    return user


@pytest.fixture
def klass(school):
    """شعبةُ تربيةٍ خاصّة: بلا جناح — وهي التي تصلها الثغرة."""
    return ClassGroupFactory(
        school=school,
        grade="G7",
        section="07/ESE",
        level_type="prep",
        academic_year=academic_year_for_school(school),
        wing=None,
    )


@pytest.fixture
def student(klass):
    user = UserFactory(full_name="طالب التربية الخاصّة", national_id="29000004001")
    StudentEnrollmentFactory(student=user, class_group=klass, enrolled_at=ENROLLED)
    return user


@pytest.fixture
def owner(school):
    return _staff(school, "ese_teacher", "معلّم الحصّة", "29000004010")


@pytest.fixture
def colleague(school):
    return _staff(school, "ese_teacher", "زميلٌ آخر", "29000004011")


@pytest.fixture
def session(school, klass, owner):
    return Session.objects.create(
        school=school,
        class_group=klass,
        teacher=owner,
        date=SUNDAY,
        start_time=dt.time(7, 10),
        end_time=dt.time(7, 55),
        status="scheduled",
    )


@pytest.fixture
def at_730(monkeypatch):
    """الساعةُ 07:30 من الأحد بتوقيت الدوحة — داخل نافذة الحصّة."""
    monkeypatch.setattr(timezone, "now", lambda: at(7, 30))


def _mark(client_as, user, session, student, status="absent"):
    return client_as(user).post(
        reverse("mark_single", args=[session.id]),
        {"student_id": str(student.id), "status": status},
    )


def test_the_session_teacher_marks_inside_the_window(client_as, at_730, session, owner, student):
    response = _mark(client_as, owner, session, student)
    assert response.status_code == 200
    row = StudentAttendance.objects.get(session=session, student=student)
    assert (row.status, row.marked_by_id) == ("absent", owner.id)


def test_another_teacher_may_not_mark_a_colleagues_session(
    client_as, at_730, session, colleague, student
):
    """الثغرةُ بعينها: زميلٌ يحمل attendance.mark يكتب حصّةَ غيره."""
    response = _mark(client_as, colleague, session, student)
    assert response.status_code == 403
    assert not StudentAttendance.objects.exists()


def test_a_coordinator_who_is_not_the_session_teacher_may_not_mark(
    client_as, at_730, school, session, student
):
    coordinator = _staff(school, "coordinator", "منسّق", "29000004012")
    response = _mark(client_as, coordinator, session, student)
    assert response.status_code == 403
    assert not StudentAttendance.objects.exists()


def test_the_teacher_may_not_mark_before_the_session_starts(
    client_as, monkeypatch, session, owner, student
):
    monkeypatch.setattr(timezone, "now", lambda: at(7, 9, 59))
    response = _mark(client_as, owner, session, student)
    assert response.status_code == 403
    assert not StudentAttendance.objects.exists()


def test_the_teacher_may_not_mark_after_the_window_closes(
    client_as, monkeypatch, session, owner, student
):
    monkeypatch.setattr(timezone, "now", lambda: at(7, 55, 1))
    response = _mark(client_as, owner, session, student)
    assert response.status_code == 403
    assert not StudentAttendance.objects.exists()


def test_the_teacher_may_not_mark_the_next_day(client_as, monkeypatch, session, owner, student):
    monkeypatch.setattr(timezone, "now", lambda: at(7, 30, day=SUNDAY + dt.timedelta(days=1)))
    response = _mark(client_as, owner, session, student)
    assert response.status_code == 403
    assert not StudentAttendance.objects.exists()


def test_the_date_is_doha_not_utc(client_as, monkeypatch, session, owner, student):
    """21:30 UTC من الأحد = 00:30 من الاثنين بالدوحة: مرفوض."""
    late = dt.datetime(2026, 9, 13, 21, 30, tzinfo=dt.UTC)
    monkeypatch.setattr(timezone, "now", lambda: late)
    response = _mark(client_as, owner, session, student)
    assert response.status_code == 403
    assert not StudentAttendance.objects.exists()


def test_a_cancelled_session_may_not_be_marked(client_as, at_730, session, owner, student):
    session.status = "cancelled"
    session.save(update_fields=["status"])
    response = _mark(client_as, owner, session, student)
    assert response.status_code == 403
    assert not StudentAttendance.objects.exists()


def test_recorders_still_mark_any_wingless_session(client_as, school, session, student):
    """أهلُ الرصد غيرُ المقيَّدين بجناح (النائبان والمدير) كما كانوا — بلا قيدِ معلّم الحصّة ولا النافذة.

    ومشرفُ الجناح مقيَّدٌ بجناحه فيرى شعبةً بلا جناحٍ 404 كما كان (قرارُ 2026-09-15) — لا شأنَ لهذا الإصلاح به.
    """
    for role, nid in (
        ("vice_admin", "29000004021"),
        ("vice_academic", "29000004022"),
        ("principal", "29000004023"),
    ):
        recorder = _staff(school, role, role, nid)
        response = _mark(client_as, recorder, session, student, status="present")
        assert response.status_code == 200, role


def test_the_developer_may_not_mark_even_as_a_superuser(
    client_as, at_730, school, session, student
):
    """D-128م: المطوّرُ لا يُدخل ولو كان superuser — لا يمرّ بـ`is_recorder` (حكمُ 0105 أ)."""
    developer = _staff(school, "platform_developer", "المطوّر", "29000004030")
    developer.is_superuser = True
    developer.save(update_fields=["is_superuser"])
    response = _mark(client_as, developer, session, student)
    assert response.status_code == 403
    assert not StudentAttendance.objects.exists()


def test_the_teachers_changes_are_audited_with_before_and_after(
    client_as, at_730, session, owner, student
):
    """D-126م: رصدُ ESE نهائيٌّ **بتدقيقٍ كامل** — كلُّ تغييرٍ سطرٌ بالقيمتين، وبالمعرّفات لا الأسماء (حكمُ 0105 ب)."""
    from core.models import AuditLog

    _mark(client_as, owner, session, student, "absent")
    _mark(client_as, owner, session, student, "present")
    lines = list(
        AuditLog.objects.filter(model_name="other", object_repr__startswith="رصدُ المعلّم").order_by(
            "timestamp"
        )
    )
    assert [line.action for line in lines] == ["create", "update"]
    assert (lines[0].changes["before"], lines[0].changes["after"]) == (None, "absent")
    assert (lines[1].changes["before"], lines[1].changes["after"]) == ("absent", "present")
    assert all(line.user_id == owner.id for line in lines)
    assert all(student.full_name not in str(line.changes) for line in lines)


def test_a_recorders_marking_is_not_double_audited_by_this_path(
    client_as, school, session, student
):
    """أهلُ الرصد لهم مساراتُهم وتدقيقُهم (كشفُ الحصص)؛ هذا السطرُ لمن لا يملك غيره."""
    from core.models import AuditLog

    recorder = _staff(school, "vice_admin", "النائب", "29000004031")
    _mark(client_as, recorder, session, student, "present")
    assert not AuditLog.objects.filter(object_repr__startswith="رصدُ المعلّم").exists()

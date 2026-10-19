"""[LEGAL] عذرُ التأخّر عن الحصّة (W-20261002-028، قرارُ المالك 2026-10-20).

الحرّاس:
- المعذورُ لا يُحسب مرّةً ولا دقائقَ في `tardiness_for` و`presence_for`، وغيرُ المعذور يُحسب.
- يعتمده معلّمُ الحصّة وحدَه، وفي يوم الحصّة فقط.
- لا يُعدَّل سطرُ الحضور، والإلغاءُ يُعيد التأخّرَ كما رُصد، ولا مخالفةَ تُنشأ.
"""

import datetime as dt

import pytest

from behavior.models import BehaviorInfraction
from operations import tardiness_excuse as service
from operations.models import Session, StudentAttendance, Subject, TardinessExcuse
from operations.presence import presence_for
from operations.tardiness import tardiness_for

pytestmark = pytest.mark.django_db

DAY = dt.date(2026, 9, 14)


@pytest.fixture
def late_row(school, class_group, teacher_user, student_user):
    subject = Subject.objects.create(school=school, name_ar="الرياضيات", code="MATH")
    session = Session.objects.create(
        school=school,
        class_group=class_group,
        teacher=teacher_user,
        subject=subject,
        date=DAY,
        start_time=dt.time(8, 0),
        end_time=dt.time(8, 45),
        status="scheduled",
    )
    return StudentAttendance.objects.create(
        session=session, student=student_user, school=school, status="late", late_minutes=12
    )


def _counts(school, student):
    tardy = tardiness_for(student, school, DAY, DAY)
    return tardy.count, tardy.minutes


def test_unexcused_lateness_is_counted(school, student_user, late_row):
    assert _counts(school, student_user) == (1, 12)


def test_excused_lateness_drops_count_and_minutes(
    school, teacher_user, student_user, late_row, enrolled_student
):
    service.grant(school, teacher_user, late_row.pk, "مراجعةُ العيادة", today=DAY)
    assert _counts(school, student_user) == (0, 0)
    entry = presence_for(student_user, school, DAY, DAY).by_subject["الرياضيات"]
    assert (entry.late_count, entry.late_minutes) == (0, 0)


def test_grant_never_edits_the_attendance_row_nor_creates_an_infraction(
    school, teacher_user, late_row
):
    service.grant(school, teacher_user, late_row.pk, today=DAY)
    late_row.refresh_from_db()
    assert (late_row.status, late_row.late_minutes) == ("late", 12)
    assert not BehaviorInfraction.objects.filter(auto_rule="period_tardy").exists()


def test_only_the_period_teacher_may_grant(school, principal_user, late_row):
    with pytest.raises(service.TardinessExcuseError):
        service.grant(school, principal_user, late_row.pk, today=DAY)
    assert not TardinessExcuse.objects.exists()


def test_grant_after_the_period_day_is_refused(school, teacher_user, late_row):
    with pytest.raises(service.TardinessExcuseError):
        service.grant(school, teacher_user, late_row.pk, today=DAY + dt.timedelta(days=1))


def test_only_late_rows_can_be_excused(school, teacher_user, late_row):
    StudentAttendance.objects.filter(pk=late_row.pk).update(status="absent")
    with pytest.raises(service.TardinessExcuseError):
        service.grant(school, teacher_user, late_row.pk, today=DAY)


def test_grant_is_idempotent_and_revoke_restores_the_lateness(
    school, teacher_user, student_user, late_row
):
    first = service.grant(school, teacher_user, late_row.pk, today=DAY)
    assert service.grant(school, teacher_user, late_row.pk, "آخر", today=DAY).pk == first.pk
    assert TardinessExcuse.objects.count() == 1
    assert service.revoke(school, teacher_user, late_row.pk, today=DAY) is True
    assert _counts(school, student_user) == (1, 12)


def test_view_lists_lates_and_grants_for_the_teacher(
    client, school, teacher_user, late_row, monkeypatch
):
    from django.urls import reverse
    from django.utils import timezone

    monkeypatch.setattr(timezone, "localdate", lambda *a, **k: DAY)
    client.force_login(teacher_user)
    page = client.get(reverse("tardiness_excuses"))
    assert page.status_code == 200
    assert late_row.student.full_name in page.content.decode()
    reply = client.post(reverse("tardiness_excuse_decide", args=[late_row.pk]), {"reason": "عيادة"})
    assert reply.status_code == 302
    assert TardinessExcuse.objects.filter(attendance=late_row).exists()

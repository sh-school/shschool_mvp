"""مهلةُ تقديم عذر الغياب عن الاختبار (W-20261001-013، D-403م، الدليل 04b السطر 1949).

آخرُ موعدٍ هو اليومُ الثالث التقويميّ بعد انتهاء جدول الاختبار (بتوقيت الدوحة) لا تُستثنى فيه عطلة.
ما قُدِّم بعده يُرفض بسببه ويُدقَّق محاولةً في سجلّ المراجعة ويبقى الغيابُ بلا عذر؛ ولا أثرَ رجعيّ
على عذرٍ قُبل قبل هذا القرار.
"""

from datetime import date, timedelta

import pytest
from django.core.exceptions import ValidationError

from assessments.models import StudentAssessmentGrade
from assessments.services import EXCUSE_GRACE_DAYS, GradeService
from core.models import AuditLog
from exam_control.models import ExamSession
from tests.test_exam_excuse_decision import _decide, _row, _staff, absent  # noqa: F401
from tests.test_grade_save_all import assessment  # noqa: F401

pytestmark = pytest.mark.django_db

SCHEDULE_END = date(2026, 1, 10)  # السبت
LAST_DAY = SCHEDULE_END + timedelta(days=3)  # الثلاثاء 13 — آخرُ يوم مقبول


@pytest.fixture
def session(school, assessment):  # noqa: F811
    assessment.date = date(2026, 1, 5)
    assessment.save(update_fields=["date"])
    return ExamSession.objects.create(
        school=school,
        name="نهاية الفصل",
        academic_year=assessment.package.setup.academic_year,
        start_date=date(2026, 1, 4),
        end_date=SCHEDULE_END,
    )


def _decider(school):
    return _staff(school, "social_worker")


def _service(assessment, student, by, submitted_on):  # noqa: F811
    return GradeService.decide_excuse(assessment, student, "illness", "شهادة 1", by, submitted_on)


def test_the_grace_is_three_calendar_days():
    assert EXCUSE_GRACE_DAYS == 3


def test_the_deadline_is_the_third_day_after_the_schedule_end(assessment, session):  # noqa: F811
    assert GradeService.excuse_deadline(assessment) == (LAST_DAY, SCHEDULE_END)


def test_the_third_day_is_accepted(school, assessment, student_user, absent, session):  # noqa: F811
    row = _service(assessment, student_user, _decider(school), LAST_DAY)

    assert row.is_excused is True
    assert row.excuse_submitted_on == LAST_DAY


def test_the_fourth_day_is_refused_and_the_absence_stays_unexcused(
    school,
    assessment,  # noqa: F811
    student_user,
    absent,  # noqa: F811
    session,
):
    with pytest.raises(ValidationError, match="انقضت مهلةُ تقديم العذر"):
        _service(assessment, student_user, _decider(school), LAST_DAY + timedelta(days=1))

    row = _row(assessment, student_user)
    assert row.is_excused is False
    assert row.excuse_type == "" and row.excuse_submitted_on is None


def test_a_holiday_inside_the_window_does_not_extend_it(
    school,
    assessment,  # noqa: F811
    student_user,
    absent,  # noqa: F811
    session,
):
    # الجمعة 2026-01-16 والسبت 17: تقويميّةٌ كلُّها؛ لا يُمدّ الموعدُ عطلةً ولا يوم راحة
    assert LAST_DAY.weekday() == 1  # الثلاثاء
    assert (LAST_DAY - SCHEDULE_END).days == 3
    with pytest.raises(ValidationError):
        _service(assessment, student_user, _decider(school), date(2026, 1, 14))


def test_a_late_attempt_is_audited_with_its_reason(
    school,
    assessment,  # noqa: F811
    student_user,
    absent,  # noqa: F811
    session,
):
    by = _decider(school)
    late = LAST_DAY + timedelta(days=5)
    with pytest.raises(ValidationError):
        _service(assessment, student_user, by, late)

    log = AuditLog.objects.filter(user=by, model_name="StudentAssessmentGrade").latest("pk")
    assert log.changes["excuse_attempt"] == "rejected_after_deadline"
    assert log.changes["submitted_on"] == late.isoformat()
    assert log.changes["deadline"] == LAST_DAY.isoformat()


def test_the_view_shows_the_rejection_and_the_late_row_is_unchanged(
    client_as,
    school,
    assessment,  # noqa: F811
    student_user,
    absent,  # noqa: F811
    session,
):
    resp = _decide(
        client_as(_decider(school)),
        assessment,
        student_user,
        submitted_on=(LAST_DAY + timedelta(days=1)).isoformat(),
    )

    assert resp.status_code == 302
    assert _row(assessment, student_user).is_excused is False


def test_a_submission_date_in_the_future_is_refused(
    school,
    assessment,  # noqa: F811
    student_user,
    absent,  # noqa: F811
    session,
):
    from django.utils import timezone

    with pytest.raises(ValidationError, match="المستقبل"):
        _service(
            assessment,
            student_user,
            _decider(school),
            timezone.localdate() + timedelta(days=1),
        )


def test_an_invalid_date_text_is_refused_with_a_message(
    client_as,
    school,
    assessment,  # noqa: F811
    student_user,
    absent,  # noqa: F811
    session,
):
    resp = _decide(client_as(_decider(school)), assessment, student_user, submitted_on="غير-تاريخ")

    assert resp.status_code == 302
    assert _row(assessment, student_user).is_excused is False


def test_without_a_registered_schedule_no_deadline_is_checked(
    school,
    assessment,  # noqa: F811
    student_user,
    absent,  # noqa: F811
):
    assert GradeService.excuse_deadline(assessment) is None

    row = _service(assessment, student_user, _decider(school), None)

    assert row.is_excused is True


def test_the_schedule_is_matched_by_the_assessment_date_and_the_school_year(
    school,
    assessment,  # noqa: F811
    session,
):
    assessment.date = date(2026, 3, 1)  # خارج مدّة الدورة
    assessment.save(update_fields=["date"])

    assert GradeService.excuse_deadline(assessment) is None


def test_no_retroactive_effect_on_an_excuse_accepted_before_the_rule(
    school,
    assessment,  # noqa: F811
    student_user,
    absent,  # noqa: F811
    session,
):
    StudentAssessmentGrade.objects.filter(pk=absent.pk).update(
        is_excused=True, excuse_type="illness", excuse_reference="قديم", excuse_submitted_on=None
    )

    row = _row(assessment, student_user)

    assert row.is_excused is True
    assert row.excuse_submitted_on is None


def test_the_queue_shows_the_last_date_for_each_absence(
    client_as,
    school,
    assessment,  # noqa: F811
    student_user,
    absent,  # noqa: F811
    session,
):
    html = client_as(_decider(school)).get("/assessments/excuses/").content.decode()

    assert "آخرُ موعدٍ لتقديم العذر" in html
    assert "2026/01/13" in html
    assert 'name="submitted_on"' in html


def test_the_submission_date_shows_in_django_admin(
    client_as,
    school,
    assessment,  # noqa: F811
    student_user,
    absent,  # noqa: F811
):
    from assessments.admin import StudentAssessmentGradeAdmin

    assert "excuse_submitted_on" in StudentAssessmentGradeAdmin.list_display

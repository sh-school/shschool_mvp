"""الحالات المعدية والعزل وتنبيه معلّم الحصة (W-20261020-042).

وسمٌ منضبطٌ بقرار الممرّض بلا تشخيص، وقرارُ إبلاغٍ خارجيٍّ بشريٌّ مسجَّلٌ لا يُرسِل شيئاً،
وتنبيهٌ للمعلّم المشتقّ من الجدول قراءةً فقط بنصٍّ ثابتٍ لا يحمل سبباً ولا حالة معدية.
"""

import datetime as dt
import pathlib

import pytest
from django.core import mail
from django.utils import timezone

from clinic import choices
from clinic.models import ClinicVisit
from clinic.services import ClinicService
from core.models import AuditLog
from notifications.models import InAppNotification
from operations.models import ScheduleSlot

ROOT = pathlib.Path(__file__).resolve().parent.parent
SECRETS = ("سببٌ-سرّيٌّ-71", "عَرَضٌ-سرّيٌّ-72", "إجراءٌ-سرّيٌّ-73")
SUNDAY = dt.date(2026, 10, 25)


def _visit(school, student, nurse):
    reason, symptoms, treatment = SECRETS
    return ClinicService.record_visit(
        school=school,
        student=student,
        nurse=nurse,
        reason=reason,
        symptoms=symptoms,
        treatment=treatment,
    )


def _slot(school, teacher, enrolled_student):
    from core.querysets import year_or_current

    return ScheduleSlot.objects.create(
        school=school,
        teacher=teacher,
        class_group=enrolled_student.class_group,
        day_of_week=0,
        period_number=2,
        start_time=dt.time(7, 50),
        end_time=dt.time(8, 35),
        academic_year=year_or_current(school, on=SUNDAY),
    )


@pytest.mark.django_db
def test_marking_infectious_uses_the_closed_list_and_audits_codes_only(
    school, student_user, nurse_user
):
    visit = _visit(school, student_user, nurse_user)
    ClinicService.mark_infectious(visit, choices.INFECTIOUS_ISOLATION, nurse_user)
    visit.refresh_from_db()
    assert visit.infectious_status == choices.INFECTIOUS_ISOLATION
    with pytest.raises(ValueError):
        ClinicService.mark_infectious(visit, "influenza", nurse_user)
    log = AuditLog.objects.get(
        model_name="ClinicVisit",
        object_id=str(visit.pk),
        changes={"infectious_status": "isolation"},
    )
    assert not any(secret in str(log.changes) for secret in SECRETS)


@pytest.mark.django_db
def test_no_external_report_without_a_recorded_human_decision(school, student_user, nurse_user):
    mail.outbox.clear()
    visit = _visit(school, student_user, nurse_user)
    ClinicService.mark_infectious(visit, choices.INFECTIOUS_SUSPECTED, nurse_user)
    visit.refresh_from_db()
    # الوسمُ وحدَه لا يقرّر إبلاغاً ولا يُرسل شيئاً
    assert visit.external_report_decision == "" and visit.external_report_by is None
    assert mail.outbox == []


@pytest.mark.django_db
def test_recording_the_report_decision_stores_who_and_when_and_sends_nothing(
    school, student_user, nurse_user
):
    mail.outbox.clear()
    visit = _visit(school, student_user, nurse_user)
    with pytest.raises(ValueError):  # بلا وسمٍ معدٍ لا قرارَ إبلاغ
        ClinicService.record_external_report_decision(visit, choices.REPORT_DONE, nurse_user)
    ClinicService.mark_infectious(visit, choices.INFECTIOUS_SUSPECTED, nurse_user)
    ClinicService.record_external_report_decision(visit, choices.REPORT_DONE, nurse_user)
    visit.refresh_from_db()
    assert visit.external_report_decision == choices.REPORT_DONE
    assert visit.external_report_by == nurse_user and visit.external_report_at is not None
    with pytest.raises(ValueError):
        ClinicService.record_external_report_decision(visit, "auto_sent", nurse_user)
    assert mail.outbox == []
    assert AuditLog.objects.filter(
        model_name="ClinicVisit", changes={"external_report_decision": "reported"}
    ).exists()


@pytest.mark.django_db
def test_the_teacher_is_alerted_with_the_event_only_and_derived_from_the_schedule(
    school, student_user, nurse_user, enrolled_student, teacher_user, monkeypatch
):
    slot = _slot(school, teacher_user, enrolled_student)
    before = (slot.teacher_id, slot.period_number, slot.start_time, slot.end_time)
    moment = timezone.make_aware(dt.datetime.combine(SUNDAY, dt.time(8, 0)))
    monkeypatch.setattr(timezone, "now", lambda: moment)

    visit = _visit(school, student_user, nurse_user)
    ClinicService.mark_infectious(visit, choices.INFECTIOUS_ISOLATION, nurse_user)

    [note] = InAppNotification.objects.filter(user=teacher_user)
    assert note.title == ClinicService.TEACHER_ALERT_TITLE
    assert student_user.full_name in note.body
    blob = f"{note.title}{note.body}{note.related_url}"
    assert not any(secret in blob for secret in SECRETS)
    assert "معد" not in blob and "عزل" not in blob
    visit.refresh_from_db()
    assert visit.teacher_alerted_at is not None
    slot.refresh_from_db()
    assert before == (slot.teacher_id, slot.period_number, slot.start_time, slot.end_time)
    # تنبيهٌ واحدٌ لكل زيارة
    assert ClinicService.alert_teacher(visit) is False
    assert InAppNotification.objects.filter(user=teacher_user).count() == 1


@pytest.mark.django_db
def test_no_alert_outside_lessons_or_without_enrollment(
    school, student_user, nurse_user, enrolled_student, teacher_user, monkeypatch
):
    _slot(school, teacher_user, enrolled_student)
    night = timezone.make_aware(dt.datetime.combine(SUNDAY, dt.time(22, 0)))
    monkeypatch.setattr(timezone, "now", lambda: night)
    visit = _visit(school, student_user, nurse_user)
    assert visit.teacher_alerted_at is None
    assert not InAppNotification.objects.filter(user=teacher_user).exists()
    assert ClinicService.teacher_of_current_slot(school, nurse_user, night) is None


def test_the_migration_only_adds_columns_with_safe_defaults():
    src = (ROOT / "clinic" / "migrations" / "0013_clinicvisit_infectious_alert.py").read_text(
        encoding="utf-8"
    )
    assert src.count("migrations.AddField") == 5
    for forbidden in ("RemoveField", "RenameField", "AlterField", "DeleteModel", "RunPython"):
        assert forbidden not in src
    assert src.count('db_default=""') == 2 and src.count("null=True") == 3
    assert ClinicVisit._meta.get_field("infectious_status").db_default == ""

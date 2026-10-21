"""
tests/test_clinic_visit_coding.py — ترميز زيارة العيادة (W-20261020-029)

القوائم المغلقة، والحقول المرمَّزة، واشتقاق الحصة قراءةً من الجدول، وبقاء النصّ الحرّ
المشفَّر خارج كلّ تجميع، وهجرةُ توسيعٍ فقط.
"""

import datetime as dt
import pathlib
import re

import pytest
from django.utils import timezone

from clinic import choices
from clinic.models import ClinicVisit
from clinic.services import ClinicService

ROOT = pathlib.Path(__file__).resolve().parent.parent


# ── القوائم المغلقة ──────────────────────────────────────────────────


def test_the_approved_lists_have_the_agreed_sizes():
    assert len(choices.SERVICES) == 21
    assert len(choices.SERVICE_GROUPS) == 7
    assert len(choices.COMPLAINT_CHOICES) == 12
    assert choices.COMPLAINT_CHOICES[-1][0] == choices.COMPLAINT_OTHER


def test_every_service_belongs_to_a_declared_group_and_codes_are_unique():
    groups = {code for code, _ in choices.SERVICE_GROUPS}
    codes = [code for code, _label, _group in choices.SERVICES]
    assert len(set(codes)) == len(codes)
    assert {group for _c, _l, group in choices.SERVICES} <= groups
    assert {group for _c, _l, group in choices.SERVICES} == groups  # لا مجموعة فارغة


def test_validators_accept_listed_codes_and_reject_the_rest():
    assert choices.is_valid_service("bandage") and not choices.is_valid_service("magic")
    assert choices.is_valid_complaint("headache") and not choices.is_valid_complaint("")
    assert choices.is_valid_outcome(choices.OUTCOME_RETURN)
    assert choices.group_of_service("insulin") == choices.GROUP_DIABETES
    assert choices.group_of_service("nope") == ""


# ── الزيارة المرمَّزة ────────────────────────────────────────────────


@pytest.mark.django_db
def test_a_new_visit_carries_service_group_complaint_and_derived_period(
    school, nurse_user, student_user, enrolled_student, teacher_user, monkeypatch
):
    from core.querysets import year_or_current
    from operations.models import ScheduleSlot

    sunday = dt.date(2026, 10, 25)
    moment = timezone.make_aware(dt.datetime.combine(sunday, dt.time(8, 0)))
    ScheduleSlot.objects.create(
        school=school,
        teacher=teacher_user,
        class_group=enrolled_student.class_group,
        day_of_week=0,
        period_number=2,
        start_time=dt.time(7, 50),
        end_time=dt.time(8, 35),
        academic_year=year_or_current(school, on=sunday),
    )
    monkeypatch.setattr(timezone, "now", lambda: moment)

    visit = ClinicService.record_visit(
        school=school,
        student=student_user,
        nurse=nurse_user,
        reason="",
        service_code="paracetamol_tablet",
        complaint_code="headache",
    )
    visit.refresh_from_db()
    assert visit.service_code == "paracetamol_tablet"
    assert visit.service_group == choices.GROUP_MEDICATION
    assert visit.complaint_code == "headache"
    assert visit.period_number == 2
    assert visit.closed_at is None and visit.outcome == ""


@pytest.mark.django_db
def test_period_is_none_outside_lessons_and_without_enrollment(
    school, nurse_user, student_user, enrolled_student
):
    sunday_night = timezone.make_aware(dt.datetime(2026, 10, 25, 22, 0))
    assert ClinicService.derive_period_number(school, student_user, sunday_night) is None
    other = nurse_user  # بلا تسجيل في شعبة
    assert ClinicService.derive_period_number(school, other, sunday_night) is None


@pytest.mark.django_db
def test_unlisted_codes_are_rejected_before_anything_is_saved(school, nurse_user, student_user):
    with pytest.raises(ValueError):
        ClinicService.record_visit(
            school=school, student=student_user, nurse=nurse_user, reason="x", service_code="magic"
        )
    with pytest.raises(ValueError):
        ClinicService.record_visit(
            school=school, student=student_user, nurse=nurse_user, reason="x", complaint_code="zzz"
        )
    assert ClinicVisit.objects.count() == 0


@pytest.mark.django_db
def test_closing_a_visit_records_outcome_and_duration_once(school, nurse_user, student_user):
    visit = ClinicService.record_visit(
        school=school, student=student_user, nurse=nurse_user, reason="x"
    )
    assert visit.duration_seconds is None
    ClinicService.close_visit(visit, choices.OUTCOME_LEAVE)
    visit.refresh_from_db()
    assert visit.outcome == choices.OUTCOME_LEAVE
    assert visit.is_sent_home is True
    assert visit.duration_seconds is not None and visit.duration_seconds >= 0
    with pytest.raises(ValueError):
        ClinicService.close_visit(visit, choices.OUTCOME_RETURN)
    with pytest.raises(ValueError):
        ClinicService.close_visit(
            ClinicService.record_visit(
                school=school, student=student_user, nurse=nurse_user, reason="y"
            ),
            "teleport",
        )


# ── النصّ الحرّ خارج كلّ تجميع ───────────────────────────────────────

_FREE_TEXT = ("reason", "symptoms", "treatment")
_AGGREGATORS = re.compile(r"\.(values|values_list|annotate|aggregate|order_by|distinct)\([^)]*")


def test_free_text_columns_never_enter_an_aggregation_or_export():
    """أيُّ استعلامٍ في العيادة يجمّع أو يُصدّر لا يلمس الأعمدةَ الحرّة المشفَّرة."""
    offenders = []
    for path in sorted((ROOT / "clinic").glob("*.py")):
        if path.name in ("models.py", "forms.py", "admin.py"):
            continue
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if _AGGREGATORS.search(line) and any(
                f'"{f}"' in line or f"'{f}'" in line for f in _FREE_TEXT
            ):
                offenders.append(f"{path.name}:{lineno}")
    assert not offenders, offenders


# ── الهجرة توسيعٌ فقط ────────────────────────────────────────────────


def test_the_coding_migration_only_adds_columns_with_safe_defaults():
    src = (ROOT / "clinic" / "migrations" / "0012_clinicvisit_coding.py").read_text(
        encoding="utf-8"
    )
    assert src.count("migrations.AddField") == 6
    for forbidden in ("RemoveField", "RenameField", "AlterField", "DeleteModel", "RunPython"):
        assert forbidden not in src
    # كلُّ عمودٍ نصّيٍّ بـ db_default، والباقي يقبل null
    assert src.count('db_default=""') == 4
    assert src.count("null=True") == 2

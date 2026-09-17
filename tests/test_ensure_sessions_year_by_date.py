"""جلساتُ تاريخٍ من عامٍ مضى تُولَّد من جدول *ذلك العام* — لا من جدول اليوم.

كان `ensure_sessions_for_date` و`resync_sessions_for_date` يشتقّان العامَ من
`academic_year_for_school(school)` — عامَ اليوم دائماً — مهما كان `target_date`.
ففتحُ شاشةٍ بتاريخٍ من أسبوعٍ مضى (`/teacher/schedule/?date=2026-04-12`، أو
`operations/views_attendance.py` و`wings/views.py` اللتين تمرّران `?date=`)
كان يولّد لذلك الأسبوع جلساتٍ من جدول العام الجاري: معلّمٌ وموادٌّ لا صلة لهما
بذلك الأسبوع، لأنّ فحصَ «الأيّام الموجودة» يعدّ جلساتِ العام الجاري وحدها
فيرى الأسبوعَ فارغاً. الدليلُ في الإنتاج: نحو 268 جلسةً من جدول 2026-2027
على تواريخ من 2026-2025 (2026-03-22 → أواخر أبريل 2026).

والإصلاحُ: عامُ *التاريخ* عبر `AcademicCalendar.year_name(school, on=target_date)`
— لا عامُ اليوم.
"""

import datetime as dt
from datetime import date

import pytest

from core.models import AcademicYear, ClassGroup
from operations.models import ScheduleSlot, Session, Subject
from operations.services import ScheduleService
from tests.conftest import MembershipFactory, RoleFactory, UserFactory

OLD_YEAR = "2025-2026"
CURRENT_YEAR = "2026-2027"

#: أحدٌ داخل نافذة العام المنقضي — نفسُ التاريخ الذي كسر الإنتاج (2026-09-17).
OLD_SUNDAY = date(2026, 4, 12)
assert OLD_SUNDAY.weekday() == 6  # الأحد


@pytest.fixture
def old_year(school):
    return AcademicYear.objects.create(
        school=school,
        name=OLD_YEAR,
        start_date=date(2025, 8, 24),
        end_date=date(2026, 6, 25),
    )


@pytest.fixture
def current_year(school):
    return AcademicYear.objects.create(
        school=school,
        name=CURRENT_YEAR,
        start_date=date(2026, 8, 23),
        end_date=date(2027, 8, 21),
    )


def _slot(school, *, academic_year, teacher_name, subject_name):
    teacher = UserFactory(full_name=teacher_name)
    MembershipFactory(user=teacher, school=school, role=RoleFactory(school=school, name="teacher"))
    cg = ClassGroup.objects.create(school=school, grade="G8", section="1", academic_year=academic_year)
    subject = Subject.objects.create(school=school, name_ar=subject_name)
    return ScheduleSlot.objects.create(
        school=school,
        teacher=teacher,
        class_group=cg,
        subject=subject,
        day_of_week=0,  # الأحد
        period_number=1,
        start_time=dt.time(7, 10),
        end_time=dt.time(7, 55),
        academic_year=academic_year,
    )


@pytest.mark.django_db
class TestSessionsUseTheDatesOwnYear:
    def test_ensure_sessions_for_a_past_date_uses_that_dates_schedule(
        self, school, old_year, current_year
    ):
        old_slot = _slot(
            school, academic_year=OLD_YEAR, teacher_name="معلّمُ العام المنقضي", subject_name="التاريخ"
        )
        _slot(
            school,
            academic_year=CURRENT_YEAR,
            teacher_name="معلّمُ العام الجاري",
            subject_name="الجغرافيا",
        )

        created = ScheduleService.ensure_sessions_for_date(school, OLD_SUNDAY)

        assert created == 1
        session = Session.objects.get(school=school, date=OLD_SUNDAY)
        assert session.teacher_id == old_slot.teacher_id
        assert session.subject_id == old_slot.subject_id
        assert session.class_group.academic_year == OLD_YEAR

    def test_resync_sessions_for_a_past_date_uses_that_dates_schedule(
        self, school, old_year, current_year
    ):
        old_slot = _slot(
            school, academic_year=OLD_YEAR, teacher_name="معلّمُ العام المنقضي", subject_name="التاريخ"
        )
        _slot(
            school,
            academic_year=CURRENT_YEAR,
            teacher_name="معلّمُ العام الجاري",
            subject_name="الجغرافيا",
        )

        result = ScheduleService.resync_sessions_for_date(school, OLD_SUNDAY)

        assert result == {"deleted": 0, "created": 1, "kept": 0}
        session = Session.objects.get(school=school, date=OLD_SUNDAY)
        assert session.teacher_id == old_slot.teacher_id
        assert session.class_group.academic_year == OLD_YEAR

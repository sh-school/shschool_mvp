"""اللوحةُ الرئيسيّة: قالبٌ لكلّ دور، وأحكامُ الأرقام في `core.dashboard_presentation`.

كان `dashboard/main.html` ألفَ سطرٍ لأحد عشر دوراً، كلٌّ بإطارٍ وبطاقاتٍ مختلفة،
وفيها أصنافٌ لا تعريفَ لها (`exec-kpi-card`، `quick-action-grid`، `kpi-info`) —
فلوحةُ فنّيّ التقنية كانت بلا تنسيقٍ أصلاً. هنا يُحرس أنّ كلَّ دورٍ يُرسم بالمكوّنات،
وأنّ أحكامَ الألوان والعناوين تقول ما يُقصد.
"""

import datetime as dt

import pytest

from core.dashboard_presentation import _delta, present
from tests.conftest import MembershipFactory, RoleFactory, UserFactory


class TestDeltaLabels:
    def test_up_down_same_and_unknown(self):
        assert _delta(3, "%") == "↑ 3% عن أمس"
        assert _delta(-2) == "↓ 2 عن أمس"
        assert _delta(0) == "= كأمس"
        assert _delta(None) == ""


class TestDirectorPresentation:
    def _ctx(self, **extra):
        base = {
            "view_type": "director",
            "today": dt.date(2026, 9, 13),
            "attendance_pct": 91,
            "completed": 3,
            "in_progress": 1,
        }
        base.update(extra)
        return present(base)

    def test_a_waiting_number_is_coloured_and_zero_is_green(self):
        assert self._ctx(pending_swaps=2)["swaps_tone"] == "orange"
        assert self._ctx(pending_swaps=0)["swaps_tone"] == "green"

    def test_critical_behaviour_turns_red_and_names_itself_once(self):
        out = self._ctx(behavior_monthly=9, behavior_critical=2)
        assert out["behavior_tone"] == "red" and out["behavior_sub"] == "2 حرجة"

    def test_sessions_detail_is_one_line(self):
        assert self._ctx()["sessions_sub"] == "3 مكتملة · 1 جارية"

    def test_the_subtitle_carries_the_date(self):
        assert self._ctx()["subtitle"].endswith("13/09/2026")


ROLE_CASES = [
    ("principal", "ui-actions"),
    ("teacher", "حصصي اليوم"),
    ("coordinator", "ما ينتظر المنسّق"),
    ("social_worker", "لوحة الأخصائي"),
    ("speech_therapist", "جدول جلسات اليوم"),
    ("activities_coordinator", "لوحة منسّق الأنشطة"),
    ("secretary", "اللوحة الإدارية"),
    ("transport_officer", "لوحة النقل المدرسي"),
    ("nurse", "زيارات العيادة"),
    ("librarian", "متأخّرةُ الإعادة"),
    ("it_technician", "الأدوات التقنيّة"),
]


@pytest.mark.django_db
@pytest.mark.parametrize("role_name,marker", ROLE_CASES)
def test_every_role_dashboard_is_drawn_with_the_shared_components(
    client_as, school, role_name, marker
):
    user = UserFactory(full_name="مستخدمُ اختبار")
    MembershipFactory(user=user, school=school, role=RoleFactory(school=school, name=role_name))

    resp = client_as(user).get("/dashboard/")

    assert resp.status_code == 200
    body = resp.content.decode()
    assert marker in body
    assert "kpi-mini" not in body
    for undefined in ("exec-kpi-card", "quick-action-grid", "kpi-info"):
        assert undefined not in body


@pytest.mark.django_db
class TestTherapistWeekStats:
    """أسبوعُ لوحة المعالج (`_get_therapist_ctx`) يبدأ الأحد لا الاثنين.

    كان `today.weekday()` (Mon=0) يُستعمل مباشرةً بداية أسبوعٍ، فيُقصي الأحدَ
    والاثنينَ من أسبوعهما الصحيح — يظهر واضحاً حين يكون اليوم الثلاثاء: حصّةُ
    الأحد قبله بيومين كانت تُحسب من الأسبوع السابق، لا هذا الأسبوع.
    """

    def _teacher_with_session(self, school, session_date):
        from core.models import ClassGroup
        from operations.models import Session, Subject

        teacher = UserFactory(full_name="معالجٌ")
        MembershipFactory(
            user=teacher, school=school, role=RoleFactory(school=school, name="speech_therapist")
        )
        cg = ClassGroup.objects.create(school=school, grade="G8", section="1")
        subject = Subject.objects.create(school=school, name_ar="علاج النطق")
        Session.objects.create(
            school=school,
            teacher=teacher,
            class_group=cg,
            subject=subject,
            date=session_date,
            start_time=dt.time(8, 0),
            end_time=dt.time(8, 45),
            status="completed",
        )
        return teacher

    def test_sundays_session_counts_in_the_week_of_the_following_tuesday(self, school):
        from core.views_dashboard import _get_therapist_ctx

        sunday = dt.date(2026, 9, 13)
        tuesday = dt.date(2026, 9, 15)
        teacher = self._teacher_with_session(school, sunday)

        ctx = _get_therapist_ctx(teacher, school, tuesday)

        assert ctx["week_total"] == 1
        assert ctx["week_completed"] == 1

    def test_a_session_from_last_school_week_is_excluded(self, school):
        from core.views_dashboard import _get_therapist_ctx

        last_thursday = dt.date(2026, 9, 10)
        tuesday = dt.date(2026, 9, 15)
        teacher = self._teacher_with_session(school, last_thursday)

        ctx = _get_therapist_ctx(teacher, school, tuesday)

        assert ctx["week_total"] == 0

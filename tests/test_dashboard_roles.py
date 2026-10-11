"""اللوحةُ الرئيسيّة: قالبٌ لكلّ دور، وأحكامُ الأرقام في `core.dashboard_presentation`.

كان `dashboard/main.html` ألفَ سطرٍ لأحد عشر دوراً، كلٌّ بإطارٍ وبطاقاتٍ مختلفة،
وفيها أصنافٌ لا تعريفَ لها (`exec-kpi-card`، `quick-action-grid`، `kpi-info`) —
فلوحةُ فنّيّ التقنية كانت بلا تنسيقٍ أصلاً. هنا يُحرس أنّ كلَّ دورٍ يُرسم بالمكوّنات،
وأنّ أحكامَ الألوان والعناوين تقول ما يُقصد.
"""

import datetime as dt

import pytest
from django.urls import reverse

from core.academic_calendar import academic_year_for_school
from core.dashboard_presentation import _delta, chunk_for_grid, present
from operations.models import AbsenceAlert
from tests.conftest import (
    ClassGroupFactory,
    MembershipFactory,
    RoleFactory,
    StudentEnrollmentFactory,
    UserFactory,
)


class TestDeltaLabels:
    def test_up_down_same_and_unknown(self):
        assert _delta(3, "%") == "↑ 3% عن أمس"
        assert _delta(-2) == "↓ 2 عن أمس"
        assert _delta(0) == "= كأمس"
        assert _delta(None) == ""


class TestChunkForGrid:
    def test_splits_sequentially_not_round_robin(self):
        assert chunk_for_grid(list(range(1, 8)), 3) == [[1, 2, 3], [4, 5, 6], [7]]

    def test_exact_multiple_gives_equal_columns(self):
        assert chunk_for_grid(list(range(1, 9)), 4) == [[1, 2], [3, 4], [5, 6], [7, 8]]

    def test_fewer_items_than_columns_gives_fewer_columns_not_empty_ones(self):
        assert chunk_for_grid([1, 2], 4) == [[1], [2]]

    def test_empty_list(self):
        assert chunk_for_grid([], 4) == []

    def test_single_column_is_the_whole_list(self):
        assert chunk_for_grid([1, 2, 3], 1) == [[1, 2, 3]]


class TestDirectorPresentation:
    def _ctx(self, **extra):
        base = {
            "view_type": "director",
            "today": dt.date(2026, 9, 13),
        }
        base.update(extra)
        return present(base)

    def test_a_waiting_number_is_coloured_and_zero_is_green(self):
        assert (
            self._ctx(pending_swaps=2)["swaps_tone"] == "amber"
        )  # نبراتُ اللوحة دلاليّةٌ: أحمر خطر، كهرمانيّ تنبيه، أخضر سليم، عنّابيّ عدّادٌ محايد (W-20261008-004 س٣)
        assert self._ctx(pending_swaps=0)["swaps_tone"] == "green"

    def test_critical_behaviour_turns_red_and_names_itself_once(self):
        out = self._ctx(behavior_monthly=9, behavior_critical=2)
        assert out["behavior_tone"] == "red" and out["behavior_sub"] == "2 حرجة"

    def test_the_subtitle_carries_the_date(self):
        assert self._ctx()["subtitle"].endswith("13/09/2026")


ROLE_CASES = [
    ("principal", "ui-actions"),
    ("teacher", "حصصي اليوم"),
    ("coordinator", "ما ينتظر المنسّق"),
    ("social_worker", "لوحة الأخصائي"),
    ("speech_therapist", "جدول جلسات اليوم"),
    ("activities_coordinator", "لوحة منسّق الأنشطة"),
    ("secretary", "لوحة السكرتير"),
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
def test_the_director_dashboard_shows_a_count_and_a_link_not_student_names(
    client_as, school, principal_user
):
    """المدير أرقامٌ ورابطٌ لا أسماءُ طلبة (D-171م، W-20261003-030): البطاقةُ تعدّ التنبيهات
    وتحيل إلى «متابعة الحضور» المحروسة بقدرتها، وفيها الأسماءُ والصفُّ والشعبة."""
    year = academic_year_for_school(school)
    klass = ClassGroupFactory(school=school, academic_year=year)
    student = UserFactory(full_name="طالبٌ متكرّر الغياب")
    StudentEnrollmentFactory(student=student, class_group=klass)
    AbsenceAlert.objects.create(
        school=school,
        student=student,
        absence_count=7,
        period_start=dt.date(2026, 9, 1),
        period_end=dt.date(2026, 9, 10),
        status="pending",
    )

    html = client_as(principal_user).get("/dashboard/").content.decode()

    assert "طالبٌ متكرّر الغياب" not in html
    assert reverse("student_affairs:attendance_overview") in html


@pytest.mark.django_db
def test_the_alerts_indicator_stays_visible_with_no_pending_alerts_and_the_grid_keeps_three_columns(
    client_as, principal_user
):
    """طلب المدير 2026-09-18: تنبيهاتُ الغياب المتكرّر لا تختفي، والشبكةُ بثلاثة أعمدةٍ لا تضطرب كلّما خلا يومٌ منها.
    W-20261008-004 (س٢، قياسُ 2026-10-08: البطاقةُ كانت تستعمل 66px من 154px): صارت مؤشّراً في «نبض الأقسام» بعدّادٍ ورابط
    يقول «لا تنبيهات معلّقة» حين تخلو، وصارت البطاقةُ الثالثةُ «سير اليوم» فالصفُّ ثلاثُ بطاقاتٍ دائماً في يوم الدوام."""
    html = client_as(principal_user).get("/dashboard/").content.decode()

    assert "تنبيهات الغياب المتكرّر" in html
    assert "لا تنبيهات معلّقة" in html
    assert 'href="/student-affairs/' in html or "attendance" in html


@pytest.mark.django_db
class TestTherapistWeekStats:
    """أسبوعُ لوحة المعالج (`get_therapist_ctx`) يبدأ الأحد لا الاثنين.

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
        from core.dashboard_selectors import get_therapist_ctx

        sunday = dt.date(2026, 9, 13)
        tuesday = dt.date(2026, 9, 15)
        teacher = self._teacher_with_session(school, sunday)

        ctx = get_therapist_ctx(teacher, school, tuesday)

        assert ctx["week_total"] == 1
        assert ctx["week_completed"] == 1

    def test_a_session_from_last_school_week_is_excluded(self, school):
        from core.dashboard_selectors import get_therapist_ctx

        last_thursday = dt.date(2026, 9, 10)
        tuesday = dt.date(2026, 9, 15)
        teacher = self._teacher_with_session(school, last_thursday)

        ctx = get_therapist_ctx(teacher, school, tuesday)

        assert ctx["week_total"] == 0


@pytest.mark.django_db
def test_the_director_numbers_share_one_card(client_as, principal_user, monkeypatch):
    """طلب المالك 2026-09-23: أرقامُ الحضور ونبضُ الأقسام في بطاقةٍ واحدة لا شريطٌ عائمٌ فوقها.

    الوقتُ مثبَّتٌ على الأحد 09:00 بتوقيت الدوحة: شريطُ «اليوم» لا يُرسم في يوم إجازة، فكان الاختبارُ
    يسقط كلَّ جمعةٍ وسبت (أسقط مجموعةَ الدمج في #895 و#905).
    """
    from django.utils import timezone

    fixed = dt.datetime(2026, 10, 11, 9, 0, tzinfo=dt.timezone(dt.timedelta(hours=3)))
    monkeypatch.setattr(timezone, "now", lambda: fixed)
    monkeypatch.setattr(timezone, "localdate", lambda *a, **k: fixed.date())
    html = client_as(principal_user).get("/dashboard/").content.decode()

    card = html[html.index("نبض المدرسة") :]
    card = card[: card.index("</section>")]
    assert 'aria-label="اليوم"' in card
    assert 'aria-label="نبض الأقسام"' in card


@pytest.mark.django_db
@pytest.mark.parametrize("prov", [True, False], ids=["جدول-مؤقّت", "جدول-فعليّ"])
@pytest.mark.parametrize("role_name", ["teacher", "coordinator"])
def test_the_shobi_card_links_once_to_the_class_grid_in_both_schedule_modes(
    client_as, school, monkeypatch, role_name, prov
):
    """W-20261010-036: بطاقةُ «شُعبي للرصد» لا تختفي بفتح الجدول — رابطٌ واحدٌ لكلّ دورٍ وفي الوضعين."""
    from operations.services import provisional_session

    monkeypatch.setattr(provisional_session, "enabled", lambda: prov)
    user = UserFactory(full_name="مستخدمُ اختبار")
    MembershipFactory(user=user, school=school, role=RoleFactory(school=school, name=role_name))

    body = client_as(user).get("/dashboard/").content.decode()

    assert "رصدُ الغياب — شُعبي" in body
    assert "لا شُعبَ مُسنَدةً إليك" in body  # بلا إسنادٍ ← رسالةٌ بلا زرّ (W-20261010-054)
    assert reverse("provisional_classes") not in body


def _assign(school, teacher, grade, section, subject):
    """إسنادٌ فعليّ لمعلّمٍ في شعبةٍ بعامها الجاري — هو ما تقرؤه `classes_for`."""
    from operations.models import SubjectClassAssignment

    klass = ClassGroupFactory(
        school=school,
        grade=grade,
        section=section,
        academic_year=academic_year_for_school(school),
    )
    SubjectClassAssignment.objects.create(
        school=school,
        class_group=klass,
        subject=subject,
        teacher=teacher,
        weekly_periods=3,
        academic_year=academic_year_for_school(school),
    )
    return klass


@pytest.mark.django_db
def test_the_shobi_card_lists_only_my_sections_in_numeric_school_order(client_as, school):
    """W-20261010-054: شُعبُ المعلّم وحدَها، رقميّاً بالصفّ ثمّ الشعبة (7/1 7/3 8/1 12/2) لا نصّيّاً، وكلٌّ برابط جدوله."""
    from operations.models import Subject

    subject = Subject.objects.create(school=school, name_ar="رياضيات", code="MAT")
    user = UserFactory(full_name="مستخدمُ اختبار")
    MembershipFactory(user=user, school=school, role=RoleFactory(school=school, name="teacher"))
    other = UserFactory(full_name="معلّمٌ آخر")
    MembershipFactory(user=other, school=school, role=RoleFactory(school=school, name="teacher"))
    mine = [
        _assign(school, user, "G12", "2", subject),
        _assign(school, user, "G8", "1", subject),
        _assign(school, user, "G7", "3", subject),
        _assign(school, user, "G7", "1", subject),
    ]
    foreign = _assign(school, other, "G9", "4", subject)

    body = client_as(user).get("/dashboard/").content.decode()
    card = body[body.index("رصدُ الغياب — شُعبي") :]

    labels = ["7/1", "7/3", "8/1", "12/2"]
    positions = [card.index(f">{label}</a>") for label in labels]
    assert positions == sorted(positions)
    for klass in mine:
        assert reverse("class_grid", args=[klass.id]) in body
    assert reverse("class_grid", args=[foreign.id]) not in body
    assert ">9/4</a>" not in body


@pytest.mark.django_db
def test_the_shobi_card_has_one_direct_link_for_a_single_section(client_as, school):
    from operations.models import Subject

    subject = Subject.objects.create(school=school, name_ar="رياضيات", code="MAT")
    user = UserFactory(full_name="مستخدمُ اختبار")
    MembershipFactory(user=user, school=school, role=RoleFactory(school=school, name="teacher"))
    only = _assign(school, user, "G7", "1", subject)

    body = client_as(user).get("/dashboard/").content.decode()

    assert body.count(reverse("class_grid", args=[only.id])) == 1
    assert "shobi-picks" not in body


@pytest.mark.django_db
@pytest.mark.parametrize("prov", [True, False], ids=["جدول-مؤقّت", "جدول-فعليّ"])
def test_the_teacher_blocks_come_in_the_decided_order(client_as, school, monkeypatch, prov):
    """W-20261010-039: ما ينتظرك ← الرصد ← الحصص ← طلابي (حصصي تُخفى مع الجدول المؤقّت كما كانت)."""
    from operations.services import provisional_session

    monkeypatch.setattr(provisional_session, "enabled", lambda: prov)
    user = UserFactory(full_name="مستخدمُ اختبار")
    MembershipFactory(user=user, school=school, role=RoleFactory(school=school, name="teacher"))

    body = client_as(user).get("/dashboard/").content.decode()
    body = body[body.index("exec-dash") :]

    marks = ["رصدُ الغياب — شُعبي"] + ([] if prov else ["حصصي اليوم"]) + ["موادّ التقييم"]
    positions = [body.find(m) for m in marks if m in body]
    assert positions == sorted(positions) and positions[0] != -1
    assert ("حصصي اليوم" in body) is (not prov)


@pytest.mark.django_db
@pytest.mark.parametrize("role_name", ["teacher", "coordinator", "teacher_assistant"])
def test_every_teacher_like_role_draws_the_dashboard_without_error(client_as, school, role_name):
    user = UserFactory(full_name="مستخدمُ اختبار")
    MembershipFactory(user=user, school=school, role=RoleFactory(school=school, name=role_name))

    resp = client_as(user).get("/dashboard/")

    assert resp.status_code == 200
    assert resp.content.decode().count(reverse("provisional_classes")) <= 1


@pytest.mark.django_db
@pytest.mark.parametrize("approved", [True, False], ids=["جدولٌ-معتمَد", "جدولٌ-غيرُ-معتمَد"])
def test_the_provisional_note_follows_the_approved_schedule_not_the_switch_alone(
    client_as, school, monkeypatch, approved
):
    """ملاحظةُ «مؤقّتاً إلى حين اعتماد الجدول» تختفي متى اعتُمد جدولٌ فعلاً ولو بقي المفتاحُ مشغَّلاً."""
    from operations.models import ScheduleGeneration, Subject
    from operations.services import provisional_session

    monkeypatch.setattr(provisional_session, "enabled", lambda: True)
    subject = Subject.objects.create(school=school, name_ar="رياضيات", code="MAT")
    user = UserFactory(full_name="مستخدمُ اختبار")
    MembershipFactory(user=user, school=school, role=RoleFactory(school=school, name="teacher"))
    _assign(school, user, "G7", "1", subject)
    _assign(school, user, "G7", "2", subject)
    ScheduleGeneration.objects.create(
        school=school,
        academic_year=academic_year_for_school(school),
        status="approved" if approved else "draft",
    )

    body = client_as(user).get("/dashboard/").content.decode()

    assert ("مؤقّتاً إلى حين اعتماد" in body) is (not approved)
    assert "اختر شعبتك" in body

"""[SCHEDULE] فحصُ الجدوى: يعدّ ولا يبحث.

    ما عجز في العدّ لا يجده بحثٌ مهما طال.

المولّدُ لا يعرف الفرقَ بين «لم أجد» و«لا يوجد»: يدور حتى ينفد وقتُه ثمّ
يخرج بحصصٍ متعذّرةٍ بلا بيان — وقد كلّف ذلك سبعمئةً وخمساً وثلاثين ثانيةً
وسقوطاً على Railway. فهذه الفحوصُ تقارن الطلبَ بالخانات قبل أن يُضغط الزرّ.

والحدُّ الأدنى للمتعذّر **أكبرُ عجزٍ لا مجموعُ الأعجاز**: الفحوصُ تتقاطع،
فمعلّمٌ ضاق وقتُه قد يكون صاحبَ المادّة التي ضاقت أيّامُها. ووعدُ المستخدم
برقمٍ أسوأَ من الحقيقة كذبٌ وإن كان في جانب الحذر.
"""

import pytest
from django.urls import reverse

from operations import schedule_feasibility as sf
from operations.models import (
    ScheduleGeneration,
    SchedulingResource,
    Subject,
    SubjectClassAssignment,
    TeacherExemption,
)

pytestmark = pytest.mark.django_db

YEAR = "2026-2027"


# ── تجهيز ────────────────────────────────────────────────────────────


@pytest.fixture
def school(db):
    from core.models import School

    return School.objects.create(name="مدرسة الشحانية", code="SHH-FEA")


def a_user(school, name, role_name):
    from tests.conftest import MembershipFactory, RoleFactory, UserFactory

    role = RoleFactory(school=school, name=role_name)
    user = UserFactory(full_name=name)
    MembershipFactory(user=user, school=school, role=role)
    return user


@pytest.fixture
def vice(db, school):
    return a_user(school, "النائب الأكاديميّ", "vice_academic")


@pytest.fixture
def teacher(db, school):
    return a_user(school, "معلّمُ الرياضيات", "teacher")


def a_subject(school, name, code, **kw):
    return Subject.objects.create(school=school, name_ar=name, code=code, **kw)


def a_class(school, grade="G8", section="1", level="prep"):
    from core.models import ClassGroup

    return ClassGroup.objects.create(
        school=school, grade=grade, section=section, level_type=level, academic_year=YEAR
    )


def assign(school, subject, class_group, teacher, periods):
    return SubjectClassAssignment.objects.create(
        school=school,
        academic_year=YEAR,
        subject=subject,
        class_group=class_group,
        teacher=teacher,
        weekly_periods=periods,
    )


def free_day(school, teacher, day):
    return TeacherExemption.objects.create(
        school=school,
        teacher=teacher,
        academic_year=YEAR,
        exemption_type="full_day",
        day_of_week=day,
        reason="اجتماعُ منسّقي المواد",
        source="school",
    )


def finding(report, code):
    return next(f for f in report.findings if f.code == code)


# ── الطاقةُ الأسبوعيّة ───────────────────────────────────────────────


def test_the_week_is_thirty_four_periods_for_prep_and_thirty_five_for_secondary():
    """الخميسُ وحدَه يفرّق: إعداديٌّ ستٌّ وثانويٌّ سبع (HC4)."""
    assert sf.weekly_capacity("prep") == 34
    assert sf.weekly_capacity("sec") == 35


def test_an_empty_school_is_feasible(school):
    report = sf.check(school, YEAR)

    assert report.feasible
    assert report.minimum_unplaceable == 0
    assert {f.status for f in report.findings} == {"ok"}


# ── طاقةُ الشعبة ─────────────────────────────────────────────────────


def test_a_class_asked_for_more_than_its_week(school, teacher):
    """أربعٌ وثلاثون خانةً في أسبوع الإعداديّ — والطلبُ خمسٌ وثلاثون."""
    section = a_class(school)
    assign(school, a_subject(school, "الرياضيات", "MAT"), section, teacher, 35)

    report = sf.check(school, YEAR)
    found = finding(report, "capacity.class")

    assert found.status == "fail"
    assert found.gap == 1
    assert not report.feasible


def test_a_class_within_its_week_passes(school, teacher):
    section = a_class(school)
    assign(school, a_subject(school, "الرياضيات", "MAT"), section, teacher, 34)

    assert finding(sf.check(school, YEAR), "capacity.class").status == "ok"


# ── طاقةُ المعلّم ────────────────────────────────────────────────────


def test_a_teacher_whose_load_exceeds_his_remaining_days(school, teacher):
    """ثلاثةُ أيّامِ تفريغٍ تترك يومين — والخميسُ منهما ستٌّ لا سبع (HC4)."""
    subject = a_subject(school, "الرياضيات", "MAT")
    assign(school, subject, a_class(school, section="1"), teacher, 15)
    assign(school, subject, a_class(school, section="2"), teacher, 15)
    for day in (0, 1, 2):
        free_day(school, teacher, day)

    found = finding(sf.check(school, YEAR), "capacity.teacher")

    assert found.status == "fail"
    assert found.gap == 30 - 13, "الأربعاءُ سبعٌ والخميسُ ستٌّ لشعبةٍ إعداديّة"
    assert "3 يومَ تفريغٍ كامل" in found.rows[0].note


def test_single_period_exemptions_narrow_the_capacity_too(school, teacher):
    """التفريغُ الجزئيُّ خاناتٌ خارجةٌ عن وقته كذلك — لا يومَ كاملاً فقط."""
    subject = a_subject(school, "الرياضيات", "MAT")
    assign(school, subject, a_class(school), teacher, 34)
    TeacherExemption.objects.create(
        school=school,
        teacher=teacher,
        academic_year=YEAR,
        exemption_type="specific_period",
        day_of_week=0,
        period_number=1,
        reason="قرار إدارة المدرسة — لا أولى ولا سابعة",
        source="school",
    )

    found = finding(sf.check(school, YEAR), "capacity.teacher")

    assert found.status == "fail", "خانةٌ واحدةٌ تكفي لقلب الميزان حين لا هامش"
    assert found.gap == 1


def test_a_teacher_with_room_passes(school, teacher):
    assign(school, a_subject(school, "الرياضيات", "MAT"), a_class(school), teacher, 20)

    assert finding(sf.check(school, YEAR), "capacity.teacher").status == "ok"


# ── الموارد ──────────────────────────────────────────────────────────


def test_a_resource_asked_for_more_than_its_slots(school, teacher):
    """معملٌ واحدٌ يسع خمساً وثلاثين حصّةً في الأسبوع — والطلبُ أربعون."""
    subject = a_subject(school, "علوم الحاسب", "CS")
    lab = SchedulingResource.objects.create(school=school, name="معمل الحاسب", capacity=1)
    lab.subjects.add(subject)
    for i in range(2):
        assign(school, subject, a_class(school, section=str(i + 1)), teacher, 20)

    found = finding(sf.check(school, YEAR), "capacity.resource")

    assert found.status == "fail"
    assert found.gap == 40 - 35


def test_two_labs_carry_twice_as_much(school, teacher):
    subject = a_subject(school, "علوم الحاسب", "CS")
    lab = SchedulingResource.objects.create(school=school, name="معملا الحاسب", capacity=2)
    lab.subjects.add(subject)
    for i in range(2):
        assign(school, subject, a_class(school, section=str(i + 1)), teacher, 20)

    assert finding(sf.check(school, YEAR), "capacity.resource").status == "ok"


# ── إسنادٌ بلا معلّم ─────────────────────────────────────────────────


def test_an_assignment_without_a_teacher_warns_but_does_not_block(school):
    """`build_tasks` يتخطّاه صامتاً — فحصصُه تضيع ولا تُعَدّ متعذّرة."""
    SubjectClassAssignment.objects.create(
        school=school,
        academic_year=YEAR,
        subject=a_subject(school, "الرياضيات", "MAT"),
        class_group=a_class(school),
        teacher=None,
        weekly_periods=4,
    )

    report = sf.check(school, YEAR)
    found = finding(report, "assignment.unassigned")

    assert found.status == "warn"
    assert report.feasible, "التنبيهُ لا يمنع"
    assert "4 حصّة" in found.summary


# ── الحكمُ الجامع ────────────────────────────────────────────────────


def test_the_minimum_is_the_largest_gap_not_their_sum(school, teacher):
    """عجزان قد يكونان عجزاً واحداً — فلا يُجمعان في وجه المستخدم."""
    subject = a_subject(school, "التكنولوجيا", "TECH")
    assign(school, subject, a_class(school), teacher, 40)

    report = sf.check(school, YEAR)

    gaps = sorted(f.gap for f in report.blocking)
    assert len(gaps) >= 2, "الشعبةُ والمعلّمُ كلاهما يشتكي"
    assert report.minimum_unplaceable == max(gaps)
    assert report.minimum_unplaceable < sum(gaps)


def test_the_report_is_storable(school, teacher):
    """يُحفظ مع عمليّة التوليد — فالحكمُ يُقرأ بعد أشهر."""
    assign(school, a_subject(school, "الرياضيات", "MAT"), a_class(school), teacher, 35)

    stored = sf.check(school, YEAR).as_dict()

    assert stored["feasible"] is False
    assert stored["minimum_unplaceable"] == 1
    assert {f["code"] for f in stored["findings"]} == {
        "capacity.class",
        "capacity.teacher",
        "capacity.resource",
        "assignment.unassigned",
        "assignment.daily_band",
        "assignment.parallel_same_teacher",
    }


# ── الشاشة ───────────────────────────────────────────────────────────


def test_the_smart_schedule_screen_shows_the_verdict(client_as, vice, school, teacher):
    assign(school, a_subject(school, "الرياضيات", "MAT"), a_class(school), teacher, 35)

    page = client_as(vice).get(f"{reverse('smart_schedule')}?year={YEAR}").content.decode()

    assert "فحصُ الجدوى قبل التوليد" in page
    assert "لن تجد موضعاً" in page
    assert "عجزٌ يقينيّ" in page


def test_a_healthy_school_is_told_so(client_as, vice, school, teacher):
    assign(school, a_subject(school, "الرياضيات", "MAT"), a_class(school), teacher, 20)

    page = client_as(vice).get(f"{reverse('smart_schedule')}?year={YEAR}").content.decode()

    assert "لا عجزَ في العدّ" in page
    assert "عجزٌ يقينيّ" not in page


# ── بوّابةُ العجز اليقينيّ (G4-أ) ────────────────────────────────────
#
# الفحصُ كان معروضاً تحذيراً فقط — الزرُّ يعمل رغمه بلا فرق. فصار العجزُ
# اليقينيّ يمنع الزرَّ افتراضيّاً، ولا يتجاوزه إلّا سببٌ صريحٌ يُسجَّل في
# AuditLog (لا في config_snapshot الذي يُستبدَل بالكامل حين يكتمل التوليدُ).


@pytest.fixture
def no_op_task(monkeypatch):
    """يعطّل إرسالَ مهمّة التوليد الفعليّة — البوّابةُ تُختبَر لا المولّد."""
    monkeypatch.setattr("operations.tasks.generate_smart_schedule_task.delay", lambda *a, **k: None)


def test_infeasible_generation_is_blocked_without_a_reason(
    client_as, vice, school, teacher, no_op_task
):
    section = a_class(school)
    assign(school, a_subject(school, "الرياضيات", "MAT"), section, teacher, 35)

    response = client_as(vice).post(reverse("smart_generate"), {"year": YEAR}, follow=True)

    assert "عجزٌ يقينيّ يمنع التوليد" in response.content.decode()
    assert not ScheduleGeneration.objects.filter(school=school, academic_year=YEAR).exists()


def test_infeasible_generation_proceeds_with_a_reason_and_is_logged(
    client_as, vice, school, teacher, no_op_task
):
    from core.models import AuditLog

    section = a_class(school)
    assign(school, a_subject(school, "الرياضيات", "MAT"), section, teacher, 35)

    response = client_as(vice).post(
        reverse("smart_generate"),
        {"year": YEAR, "feasibility_override_reason": "جدولٌ مؤقّتٌ لحين تعديل الإسناد"},
        follow=True,
    )

    assert response.status_code == 200
    generation = ScheduleGeneration.objects.get(school=school, academic_year=YEAR)
    log = AuditLog.objects.get(
        school=school,
        object_id=str(generation.pk),
        changes__event="schedule_generate_despite_infeasibility",
    )
    assert log.changes["reason"] == "جدولٌ مؤقّتٌ لحين تعديل الإسناد"
    assert log.changes["minimum_unplaceable"] == 1


def test_a_feasible_generation_needs_no_reason(client_as, vice, school, teacher, no_op_task):
    """لا عجزَ في العدّ → الزرُّ العاديّ يعمل كما كان، بلا سببٍ ولا سجلّ تجاوز."""
    from core.models import AuditLog

    assign(school, a_subject(school, "الرياضيات", "MAT"), a_class(school), teacher, 20)

    response = client_as(vice).post(reverse("smart_generate"), {"year": YEAR}, follow=True)

    assert response.status_code == 200
    assert ScheduleGeneration.objects.filter(school=school, academic_year=YEAR).exists()
    assert not AuditLog.objects.filter(
        changes__event="schedule_generate_despite_infeasibility"
    ).exists()


# ── AS-1/AS-4/AS-5: النصابُ مقابلَ سقف الجرس الفعليّ ─────────────────


def test_a_personal_cap_tighter_than_the_bell_blocks_the_load(school, teacher):
    """تفضيلٌ شخصيٌّ أضيقُ من الجرس هو الحاكم (AS-4) — والمنصّةُ تسمّيه."""
    from operations.models import TeacherPreference

    TeacherPreference.objects.create(
        school=school, teacher=teacher, academic_year=YEAR, max_daily_periods=2
    )
    subject = a_subject(school, "الرياضيات", "MAT")
    assign(school, subject, a_class(school), teacher, 15)  # 5 أيّام × 2 = 10 أقصى

    found = finding(sf.check(school, YEAR), "assignment.daily_band")

    assert found.status == "fail"
    assert found.rows[0].capacity == 10
    assert "تفضيلُه الشخصيّ" in found.rows[0].note


def test_margin_free_edge_warns_without_blocking(school, teacher):
    """على الحدّ بلا هامشٍ يُحذَّر لا يُرفَض — والتوليدُ لا يُمنع بتحذير."""
    from operations.models import TeacherPreference

    TeacherPreference.objects.create(
        school=school, teacher=teacher, academic_year=YEAR, max_daily_periods=4
    )
    subject = a_subject(school, "الرياضيات", "MAT")
    assign(school, subject, a_class(school), teacher, 20)  # 5 × 4 = 20، هامشٌ صفر

    report = sf.check(school, YEAR)
    found = finding(report, "assignment.daily_band")

    assert found.status == "warn"
    assert report.feasible, "التحذيرُ لا يحجب — لا هامشَ لا استحالة"


def test_a_teacher_with_margin_passes_the_daily_band_check(school, teacher):
    subject = a_subject(school, "الرياضيات", "MAT")
    assign(school, subject, a_class(school), teacher, 10)

    assert finding(sf.check(school, YEAR), "assignment.daily_band").status == "ok"


# ── AS-2: تمايزُ معلّمي المجموعة المتوازية ────────────────────────────


def test_the_same_teacher_on_both_sides_of_a_parallel_group_is_a_silent_breach(school, teacher):
    """معلّمٌ واحدٌ لعضوَي مجموعةٍ متوازية — خرقٌ لا يراه HC1 (AS-2)."""
    section = a_class(school)
    SubjectClassAssignment.objects.create(
        school=school,
        academic_year=YEAR,
        subject=a_subject(school, "الفنون", "ART"),
        class_group=section,
        teacher=teacher,
        weekly_periods=2,
        parallel_group="فنون-تكنولوجيا",
    )
    SubjectClassAssignment.objects.create(
        school=school,
        academic_year=YEAR,
        subject=a_subject(school, "التكنولوجيا", "TECH"),
        class_group=section,
        teacher=teacher,
        weekly_periods=2,
        parallel_group="فنون-تكنولوجيا",
    )

    found = finding(sf.check(school, YEAR), "assignment.parallel_same_teacher")

    assert found.status == "fail"
    assert found.rows[0].demand == 2 and found.rows[0].capacity == 1
    assert "معلّمُ الرياضيات" in found.rows[0].note


def test_different_teachers_on_a_parallel_group_pass(school, teacher):
    other = a_user(school, "معلّمةُ الفنون", "teacher")
    section = a_class(school)
    SubjectClassAssignment.objects.create(
        school=school,
        academic_year=YEAR,
        subject=a_subject(school, "الفنون", "ART"),
        class_group=section,
        teacher=teacher,
        weekly_periods=2,
        parallel_group="فنون-تكنولوجيا",
    )
    SubjectClassAssignment.objects.create(
        school=school,
        academic_year=YEAR,
        subject=a_subject(school, "التكنولوجيا", "TECH"),
        class_group=section,
        teacher=other,
        weekly_periods=2,
        parallel_group="فنون-تكنولوجيا",
    )

    assert finding(sf.check(school, YEAR), "assignment.parallel_same_teacher").status == "ok"


def test_the_generate_button_hides_when_infeasible_and_the_override_form_appears(
    client_as, vice, school, teacher
):
    section = a_class(school)
    assign(school, a_subject(school, "الرياضيات", "MAT"), section, teacher, 35)

    page = client_as(vice).get(f"{reverse('smart_schedule')}?year={YEAR}").content.decode()

    assert "بدء التوليد" not in page
    assert "ولِّد على أيّ حال" in page
    assert "سببُ التوليد رغم العجز" in page


# ── AS-1: سقفُ الجرس بالأوقات الفعليّة (وإصلاحُ عدّ التكتّلات) ──────────


def a_bell(school, band, spans, day_types=("regular", "thursday")):
    """جرسٌ لنطاق: spans قائمةُ (بدء، انتهاء) بـ"س:د" — رقمُ الحصّة ترتيبُها."""
    from datetime import time

    from operations.models import TimeSlotConfig

    for day_type in day_types:
        for number, (start, end) in enumerate(spans, 1):
            sh, sm = map(int, start.split(":"))
            eh, em = map(int, end.split(":"))
            TimeSlotConfig.objects.create(
                school=school,
                band=band,
                period_number=number,
                start_time=time(sh, sm),
                end_time=time(eh, em),
                day_type=day_type,
            )


SEVEN_BACK_TO_BACK = [
    ("07:00", "07:45"),
    ("07:50", "08:35"),
    ("08:40", "09:25"),
    ("09:30", "10:15"),
    ("10:20", "11:05"),
    ("11:10", "11:55"),
    ("12:00", "12:45"),
]


def test_a_back_to_back_bell_caps_at_four_a_day_not_one(school):
    """سبعُ حصصٍ بفاصل خمس دقائق ⇒ ٤ لا ١ — HC5 يمنع المتلاصقتين لا اليومَ كلَّه."""
    a_bell(school, None, SEVEN_BACK_TO_BACK)

    assert sf._band_day_cap(school, frozenset({""}), "regular") == 4


def test_a_normal_load_is_not_flagged_on_a_realistic_bell(school, teacher):
    """نصابٌ ١٤ على جرسٍ متتالٍ (سقفُه ١٧ بعد HC8) لا يُحجَب — العدُّ بالتكتّلات كان يحجبه."""
    a_bell(school, None, SEVEN_BACK_TO_BACK)
    assign(school, a_subject(school, "الرياضيات", "MAT"), a_class(school), teacher, 14)

    assert finding(sf.check(school, YEAR), "assignment.daily_band").status == "ok"


def test_two_bands_union_caps_below_the_sum_of_their_bells(school, teacher):
    """AS-1: خانةُ نطاقٍ تتلاصق بالساعة مع خانة نطاقٍ آخر — الاتّحادُ لا يزيد السقف."""
    from core.models import ClassGroup, TimeBand

    ground = TimeBand.objects.create(school=school, code="g", name="أرضيّ")
    upper = TimeBand.objects.create(school=school, code="u", name="علويّ")
    a_bell(school, ground, [("07:00", "07:45"), ("08:00", "08:45")])
    a_bell(school, upper, [("07:50", "08:35"), ("08:50", "09:35")])
    subject = a_subject(school, "الرياضيات", "MAT")
    for section, band in (("1", ground), ("2", upper)):
        klass = ClassGroup.objects.create(
            school=school,
            grade="G8",
            section=section,
            level_type="prep",
            academic_year=YEAR,
            time_band=band,
        )
        assign(school, subject, klass, teacher, 6)  # 12 > 5 أيّام × 2

    found = finding(sf.check(school, YEAR), "assignment.daily_band")

    assert found.status == "fail"
    assert found.rows[0].capacity == 10, "اتّحادُ الخانات ٢ في اليوم لا مجموعُ سقفَي النطاقين"
    assert "سقفُ الجرس" in found.rows[0].note


def test_a_clean_report_says_no_blocker_was_found_not_that_it_is_valid(school, teacher):
    """AS-6: الفحصُ يثبت الاستحالةَ لا الإمكان، فرسالةُ النجاح تقول ذلك."""
    assign(school, a_subject(school, "الرياضيات", "MAT"), a_class(school), teacher, 10)

    report = sf.check(school, YEAR)

    for code in ("assignment.daily_band", "assignment.parallel_same_teacher"):
        summary = finding(report, code).summary
        assert summary.startswith("لم يُكتشف مانع")
        assert "صالح" not in summary


# ── عند الإدخال: الفحصُ موصولٌ بمسار الإسناد لا بالتوليد وحدَه ─────────


def _apply(svc, school, section, subject, who, vice, periods, **kw):
    return svc.apply_assignment(
        school=school,
        academic_year=YEAR,
        class_group=section,
        subject=subject,
        teacher=who,
        weekly_periods=periods,
        by=vice,
        **kw,
    )


def test_entry_rejects_a_load_beyond_the_personal_cap_and_names_it(school, teacher, vice):
    from academic_management import assignment_services as svc
    from operations.models import TeacherPreference

    TeacherPreference.objects.create(
        school=school, teacher=teacher, academic_year=YEAR, max_daily_periods=2
    )
    subject = a_subject(school, "الرياضيات", "MAT")

    with pytest.raises(svc.AssignmentError) as raised:
        _apply(svc, school, a_class(school), subject, teacher, vice, 11)  # فوق 5 × 2

    blocked = [f for f in raised.value.findings if f.code == svc.BAND_LOAD_IMPOSSIBLE]
    assert blocked and "تفضيلُه الشخصيّ" in blocked[0].message
    assert not SubjectClassAssignment.objects.filter(subject=subject).exists()


def test_entry_accepts_a_load_within_every_cap(school, teacher, vice):
    from academic_management import assignment_services as svc

    subject = a_subject(school, "الرياضيات", "MAT")
    row, findings = _apply(svc, school, a_class(school), subject, teacher, vice, 10)

    assert row.pk
    assert not [f for f in findings if f.code == svc.BAND_LOAD_IMPOSSIBLE]


def test_entry_rejects_the_same_teacher_twice_in_one_parallel_group(school, teacher, vice):
    from academic_management import assignment_services as svc

    section = a_class(school)
    art = a_subject(school, "الفنون", "ART")
    tech = a_subject(school, "التكنولوجيا", "TECH")
    _apply(svc, school, section, art, teacher, vice, 2, parallel_group="فنون-تكنولوجيا")

    with pytest.raises(svc.AssignmentError) as raised:
        _apply(svc, school, section, tech, teacher, vice, 2, parallel_group="فنون-تكنولوجيا")

    blocked = [f for f in raised.value.findings if f.code == svc.PARALLEL_SAME_TEACHER]
    assert blocked and "الفنون" in blocked[0].message
    assert not SubjectClassAssignment.objects.filter(subject=tech).exists()


def test_entry_accepts_a_different_teacher_on_the_same_parallel_group(school, teacher, vice):
    from academic_management import assignment_services as svc

    other = a_user(school, "معلّمةُ التكنولوجيا", "teacher")
    section = a_class(school)
    for subject, who in (
        (a_subject(school, "الفنون", "ART"), teacher),
        (a_subject(school, "التكنولوجيا", "TECH"), other),
    ):
        row, _ = _apply(
            svc, school, section, subject, who, vice, 2, parallel_group="فنون-تكنولوجيا"
        )
        assert row.pk


# ── سقفُ السابعة (HC8) في سعة المعلّم — W-20261003-035 ────────────────────


def _pref(school, teacher, **kw):
    from operations.models import TeacherPreference

    return TeacherPreference.objects.create(
        school=school, teacher=teacher, academic_year=YEAR, max_daily_periods=7, **kw
    )


def test_the_seventh_period_limit_lowers_a_teachers_real_cap(school, teacher):
    """٣ خاناتٍ مستقلّةٍ يومياً بلا السابعة و٤ معها، وسابعتان فقط ⇒ ٥×٣+٢ = ١٧ لا ٢٠.

    معلّمٌ نصابُه ١٨ على هذا الجرس حصّةٌ منه لا موضعَ لها بأيّ خوارزميّة — وكان الفحصُ يقول ٢٠ فيمرّ.
    """
    a_bell(school, None, SEVEN_BACK_TO_BACK)
    assign(school, a_subject(school, "الرياضيات", "MAT"), a_class(school), teacher, 18)

    found = finding(sf.check(school, YEAR), "assignment.daily_band")

    assert found.status == "fail"
    assert found.rows[0].capacity == 17 and found.rows[0].gap == 1
    assert "HC8" in found.rows[0].note


def test_a_personal_seventh_cap_of_three_lifts_that_teacher_alone(school, teacher):
    """سقفٌ شخصيٌّ ٣ يجعل سعتَه ١٨ فيحلّ العجز (ويبقى على الحدّ بلا هامش: تحذيرٌ لا رفض)."""
    a_bell(school, None, SEVEN_BACK_TO_BACK)
    other = a_user(school, "معلّمُ العلوم", "teacher")
    assign(school, a_subject(school, "الرياضيات", "MAT"), a_class(school), teacher, 18)
    assign(school, a_subject(school, "العلوم", "SCI"), a_class(school, section="2"), other, 18)
    _pref(school, teacher, max_last_periods=3)

    rows = {r.name: r for r in finding(sf.check(school, YEAR), "assignment.daily_band").rows}

    assert rows[teacher.full_name].capacity == 18 and "على حدّ" in rows[teacher.full_name].note
    assert rows[other.full_name].capacity == 17, "غيرُه يبقى على السقف العامّ"


def test_entry_rejects_the_eighteenth_period_unless_the_teacher_has_a_seventh_cap(school, teacher):
    a_bell(school, None, SEVEN_BACK_TO_BACK)
    section = a_class(school)

    refused = sf.entry_load_violation(school, YEAR, teacher, section, 18)
    assert refused and "HC8" in refused and "17" in refused

    _pref(school, teacher, max_last_periods=3)
    assert sf.entry_load_violation(school, YEAR, teacher, section, 18) is None


def test_build_tasks_carries_only_a_written_seventh_cap(school, teacher):
    """السقفُ يُحمل إلى `Member` لمن كُتب له فقط؛ الصفرُ يعني العامّ."""
    from operations import scheduler

    other = a_user(school, "معلّمُ العلوم", "teacher")
    assign(school, a_subject(school, "الرياضيات", "MAT"), a_class(school, section="1"), teacher, 2)
    assign(school, a_subject(school, "العلوم", "SCI"), a_class(school, section="2"), other, 2)
    _pref(school, teacher, max_last_periods=3)
    _pref(school, other)  # سجلٌّ بلا سقف سابعة

    caps = {
        m.teacher_id: m.last_cap for t in scheduler.build_tasks(school, YEAR) for m in t.members
    }

    assert caps == {str(teacher.id): 3, str(other.id): 0}


def test_an_out_of_range_seventh_cap_is_read_as_absent(school, teacher):
    """شرطُ 0105: إدخالٌ مباشرٌ بالـORM لا يمرّ بالـvalidators (0 أو 99) لا يتحوّل إلى إلغاء HC8."""
    from operations import scheduler

    a_bell(school, None, SEVEN_BACK_TO_BACK)
    assign(school, a_subject(school, "الرياضيات", "MAT"), a_class(school), teacher, 2)
    section = a_class(school, section="9")
    for bad in (0, 99):
        pref = _pref(school, teacher, max_last_periods=bad)

        member = scheduler.build_tasks(school, YEAR)[0].members[0]
        assert member.last_cap == 0, f"{bad} يُقرأ غيابَ سقف"
        assert sf.entry_load_violation(school, YEAR, teacher, section, 18)
        pref.delete()


def test_the_teacher_screen_never_writes_the_admin_seventh_cap(client_as, school, teacher):
    """شرطُ 0105: الحفظ بـ`update_fields` فلا يمحو سقفاً عدّله مديرٌ بين الجلب والحفظ."""
    from unittest import mock

    from operations.models import TeacherPreference

    pref = _pref(school, teacher, max_last_periods=3)
    with mock.patch.object(TeacherPreference, "save", autospec=True) as spy:
        client_as(teacher).post(
            f"{reverse('teacher_preferences')}?year={YEAR}",
            {"max_daily_periods": "5", "max_consecutive": "3"},
        )

    assert spy.called
    written = spy.call_args.kwargs["update_fields"]
    assert "max_last_periods" not in written and "updated_at" in written
    pref.refresh_from_db()
    assert pref.max_last_periods == 3


def test_changing_the_seventh_cap_in_admin_leaves_an_audit_trail_without_a_name(
    school, teacher, vice
):
    """توصيةُ 0105: قيمتان قبل وبعد ومعرّفُ الصفّ — لا اسمُ المعلّم (قاعدة W-019)."""
    from django.contrib.admin.sites import AdminSite
    from django.test import RequestFactory

    from core.models import AuditLog
    from operations.admin import TeacherPreferenceAdmin
    from operations.models import TeacherPreference

    pref = _pref(school, teacher)
    request = RequestFactory().post("/")
    request.user = vice
    admin = TeacherPreferenceAdmin(TeacherPreference, AdminSite())

    pref.max_last_periods = 3
    admin.save_model(request, pref, None, True)
    log = AuditLog.objects.get(changes__event="teacher_last_period_cap_changed")
    assert log.changes["before"] is None and log.changes["after"] == 3
    assert log.object_id == str(pref.pk) and teacher.full_name not in log.object_repr

    admin.save_model(request, pref, None, True)  # بلا تغيير ⇒ لا سطرَ جديد
    assert AuditLog.objects.filter(changes__event="teacher_last_period_cap_changed").count() == 1

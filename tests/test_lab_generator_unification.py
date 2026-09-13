"""[SCHEDULE] المختبرُ والمولّدُ يتّفقان — مصدرٌ واحدٌ ووزنٌ لم يُقصَد يزول.

    ما يقيسه المقياسُ هو ما يوجّهه الترجيح.

المختبرُ ليس مرآةً تُقرأ بعد الحدث: `grid_lab_score` يقيس كلَّ محاولةِ توليدٍ
فتدخل درجتُه مفتاحَ المفاضلة، و`scheduler_improve` يقبل كلَّ نقلةٍ ترفعها. فما
اختلّ في المقياس قاد الجدولَ لا وصفه.

وهذه الاختباراتُ تحرس ثلاثة:

    الوزنُ لا يُحابي   درجةُ المؤشّر لا تتضخّم لأنّ حقيبتَه صغيرة
    المصدرُ واحد       `Subject.pedagogy` يوجّه الترجيحَ كما يقيس المختبر
    الحدُّ واحد        النصفُ الأوّل من اليوم رقمٌ واحدٌ في الموضعين
"""

import pytest

from operations.schedule_lab import CATALOG, MORNING_LAST, metric_score, overall_score
from operations.scheduler import ScheduleGrid, Task
from operations.scheduler_constraints import check_last_period_share, evaluate_soft_constraints

pytestmark = pytest.mark.django_db


def task(**kw):
    fields = {
        "class_id": "c1",
        "class_name": "7/1",
        "subject_id": "s1",
        "subject_name": "مادّة",
        "subject_code": "XXX",
        "teacher_id": "t1",
        "teacher_name": "معلّم",
        "weekly_periods": 4,
        "level_type": "prep",
        "grade": "G8",
    }
    fields.update(kw)
    return Task(**fields)


def _full_metrics(**overrides) -> dict:
    """مؤشّراتٌ كاملةٌ بقيمةٍ مثاليّةٍ لكلّ مفتاح — ثمّ يُنزَل ما يُطلب."""
    out = {}
    for key, (_, _, better) in CATALOG.items():
        out[key] = {"value": 100 if better == "high" else 0}
    for key, value in overrides.items():
        out[key.replace("__", ".")] = {"value": value}
    return out


# ── الوزنُ لا يُحابي حقيبةً صغيرة ────────────────────────────────────


def test_a_metric_weighs_the_same_wherever_its_bucket_is():
    """«الرياضياتُ في السادسة» كان يزن أربعةَ أضعافٍ ونصفاً «أطولَ تتابع».

    والسببُ أنّ الدرجةَ كانت متوسّطَ المجموعات: تسعةُ مؤشّراتٍ ليوم المعلّم
    تتقاسم سُدساً، ومؤشّرا الشعبة يتقاسمان سُدساً مثلَه.
    """
    base = overall_score(_full_metrics())
    from_crowded = base - overall_score(_full_metrics(teacher__run_breaches=10))
    from_sparse = base - overall_score(_full_metrics(class__heavy_streak_days=10))

    assert from_crowded > 0 and from_sparse > 0
    assert from_crowded == pytest.approx(from_sparse), "حقيبةُ المؤشّر لا تزيده وزناً"


def test_the_score_is_the_mean_of_the_metrics_themselves():
    metrics = _full_metrics(teacher__run_breaches=5, class__maths_late=20)
    scores = [s for key in CATALOG if (s := metric_score(key, metrics[key]["value"])) is not None]

    assert overall_score(metrics) == pytest.approx(round(sum(scores) / len(scores), 2))


def test_a_perfect_schedule_still_scores_a_hundred():
    assert overall_score(_full_metrics()) == 100.0


# ── المصدرُ واحد: طبيعةُ المادّة من القاعدة ──────────────────────────


def _penalty_for(**kw) -> dict:
    grid = ScheduleGrid()
    return evaluate_soft_constraints(grid, 0, kw.pop("period"), task(**kw)).details


def test_the_heavy_subject_penalty_follows_pedagogy_not_the_code():
    """كانت `CORE_CODES` قائمةً محفورةً؛ والمختبرُ يقيس بـ`pedagogy` — فافترقا."""
    late = MORNING_LAST + 1

    assert "core_early" in _penalty_for(period=late, pedagogy="heavy")
    assert "core_early" not in _penalty_for(period=late, pedagogy="regular")
    assert "core_early" not in _penalty_for(
        period=late, subject_code="MAT"
    ), "الرمزُ وحدَه لا يُثقِّل — الصفةُ في القاعدة"


def test_the_heavy_penalty_uses_the_labs_own_boundary():
    """الحدُّ `MORNING_LAST` نفسُه: كان الترجيحُ يعاقب السادسةَ والمقياسُ يعدّ الخامسة."""
    assert "core_early" not in _penalty_for(period=MORNING_LAST, pedagogy="heavy")
    assert "core_early" in _penalty_for(period=MORNING_LAST + 1, pedagogy="heavy")


def test_the_activity_penalty_follows_pedagogy_and_the_same_boundary():
    """كانت البدنيّةَ وحدَها بالرمز في (٤،٥)؛ وصارت كلَّ نشاطٍ في النصف الثاني."""
    assert "pe_after_break" in _penalty_for(period=1, pedagogy="activity")
    assert "pe_after_break" not in _penalty_for(period=MORNING_LAST + 1, pedagogy="activity")
    assert "pe_after_break" not in _penalty_for(period=1, subject_code="PE"), "الرمزُ وحدَه لا يوجّه"


# ── ما يقطع سلسلةَ التلاصق: مكانٌ أو نشاط ────────────────────────────


def test_a_place_change_breaks_the_streak():
    """موردٌ مسجَّلٌ — ملعبٌ أو معملٌ — يُخرج المعلّمَ من صفّه فيقطع السلسلة."""
    grid = ScheduleGrid()
    grid.place(0, 1, task(class_id="a", subject_id="sa"))
    grid.place(0, 2, task(class_id="b", subject_id="sb", resources=(("r1", 2, False),)))

    assert grid.teacher_consecutive_counted("t1", 0, 3) == 0


def test_an_activity_breaks_the_streak_even_without_a_resource():
    """ومدرسةٌ لم تُسجّل ملعباً تبقى بدنيّتُها قاطعةً بطبيعتها."""
    grid = ScheduleGrid()
    grid.place(0, 1, task(class_id="a", subject_id="sa"))
    grid.place(0, 2, task(class_id="b", subject_id="sb", pedagogy="activity"))

    assert grid.teacher_consecutive_counted("t1", 0, 3) == 0


def test_an_ordinary_lesson_does_not_break_it():
    grid = ScheduleGrid()
    grid.place(0, 1, task(class_id="a", subject_id="sa"))
    grid.place(0, 2, task(class_id="b", subject_id="sb"))

    assert grid.teacher_consecutive_counted("t1", 0, 3) == 2


# ── والمولّدُ يقرأ الحقلَ من القاعدة ─────────────────────────────────


def test_build_tasks_carries_the_pedagogy_from_the_database():
    """الحلقةُ تُغلَق: ما تكتبه الإدارةُ في الشاشة يصل مهمّةَ المولّد."""
    from core.models import ClassGroup, School
    from operations.models import Subject, SubjectClassAssignment
    from operations.scheduler import build_tasks
    from tests.conftest import MembershipFactory, RoleFactory, UserFactory

    year = "2026-2027"
    school = School.objects.create(name="مدرسة الشحانية", code="SHH-UNI")
    teacher = UserFactory(full_name="معلّمُ الفنّيّة")
    MembershipFactory(user=teacher, school=school, role=RoleFactory(school=school, name="teacher"))
    SubjectClassAssignment.objects.create(
        school=school,
        academic_year=year,
        subject=Subject.objects.create(
            school=school, name_ar="الفنون البصرية", code="ART", pedagogy="activity"
        ),
        class_group=ClassGroup.objects.create(
            school=school, grade="G8", section="1", level_type="prep", academic_year=year
        ),
        teacher=teacher,
        weekly_periods=2,
    )

    built = build_tasks(school, year)

    assert built and {t.pedagogy for t in built} == {"activity"}


# ── طرفا اليوم سواء: الأولى كالسابعة (قرار الإدارة 2026-09-10) ───────


def test_the_first_period_now_weighs_like_the_seventh():
    """المقياسُ يعدّهما في سلّةٍ واحدةٍ منذ كُتب، والترجيحُ صار يوافقه."""
    from operations.scheduler_constraints import LAST_PERIOD

    grid = ScheduleGrid()
    grid.place(0, 1, task(class_id="a", subject_id="sa"))

    at_first = evaluate_soft_constraints(grid, 1, 1, task(class_id="b", subject_id="sb")).details
    at_last = evaluate_soft_constraints(
        grid, 1, LAST_PERIOD, task(class_id="b", subject_id="sb")
    ).details
    in_middle = evaluate_soft_constraints(grid, 1, 3, task(class_id="b", subject_id="sb")).details

    assert at_first["extra_edge_period"] == at_last["extra_edge_period"] > 0
    assert "extra_edge_period" not in in_middle


def test_the_edge_counter_adds_both_ends():
    from operations.scheduler_constraints import LAST_PERIOD

    grid = ScheduleGrid()
    grid.place(0, 1, task(class_id="a", subject_id="sa"))
    grid.place(1, LAST_PERIOD, task(class_id="b", subject_id="sb"))

    assert grid.teacher_edge_periods("t1") == 2
    assert grid.teacher_periods_at("t1", 1) == 1
    assert grid.teacher_periods_at("t1", LAST_PERIOD) == 1


def test_only_the_seventh_keeps_a_hard_cap():
    """الترجيحُ يعدّ الطرفين، والمنعُ للسابعة وحدَها — والقياسُ هو الذي فرّق.

    منعُ الأولى صلباً أنتج خمسَ حصصٍ بلا موضعٍ من 869 (قياس 2026-09-10):
    خانةُ الأولى مئةٌ وخمسٌ وعشرون على ثلاثةٍ وسبعين معلّماً، فالسقفُ عليها
    يُغلق ما لا يُفتح بغيره.
    """
    from operations.scheduler_constraints import LAST_PERIOD

    grid = ScheduleGrid()
    for day, klass in ((0, "a"), (1, "b")):
        grid.place(day, 1, task(class_id=klass, subject_id=f"s{klass}"))
        grid.place(day, LAST_PERIOD, task(class_id=f"x{klass}", subject_id=f"z{klass}"))

    assert check_last_period_share(
        grid, 1, task(class_id="c", subject_id="sc")
    ), "الأولى تُثقَّل ولا تُمنع"
    assert not check_last_period_share(
        grid, LAST_PERIOD, task(class_id="c", subject_id="sc")
    ), "والسابعةُ بلغت سقفَها"


def test_the_seventh_is_not_repeated_on_the_same_class():
    from operations.scheduler_constraints import LAST_PERIOD

    grid = ScheduleGrid()
    grid.place(0, LAST_PERIOD, task(class_id="a", subject_id="sa"))

    assert not check_last_period_share(grid, LAST_PERIOD, task(class_id="a", subject_id="s2"))
    assert check_last_period_share(grid, LAST_PERIOD, task(class_id="b", subject_id="s2"))

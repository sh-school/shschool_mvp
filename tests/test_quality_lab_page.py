"""صفحةُ مختبر الجودة: بوّابةٌ ورادارٌ وبطاقاتٌ بفرقها عن المرجع، وحفظُ أساس."""

import re

import pytest
from django.urls import reverse

from operations.models import ScheduleBaseline, Subject, SubjectClassAssignment
from operations.schedule_lab import metric_score, section_scores
from tests.conftest import ClassGroupFactory, MembershipFactory, RoleFactory, UserFactory

pytestmark = pytest.mark.django_db
YEAR = "2026-2027"


def test_scores_are_monotone_and_bounded():
    assert metric_score("validity.hard_conflicts", 0) == 100.0
    assert metric_score("validity.hard_conflicts", 3) == 70.0
    assert metric_score("teacher.gap_weighted_avg", 0) == 100.0
    assert metric_score("teacher.gap_weighted_avg", 1) == 50.0
    assert metric_score("teacher.compactness", 1.0) == 100.0
    assert metric_score("teacher.compactness", 2.0) == 50.0
    assert metric_score("teacher.run_breaches", 42) == 58.0
    assert metric_score("fairness.edge_cv", 0.25) == 75.0
    assert metric_score("subject.pattern_match", 99.0) == 99.0
    assert metric_score("resources.utilization", 63.8) is None, "معلومةٌ لا درجة"
    assert metric_score("class.maths_late", None) is None


def test_section_scores_average_their_metrics():
    metrics = {
        "validity.hard_conflicts": {"value": 0},
        "validity.completeness": {"value": 100.0},
        "validity.uncovered_days": {"value": 0},
        "teacher.gap_weighted_avg": {"value": 1.0},
    }
    scores = section_scores(metrics)
    assert scores["validity"] == 100.0
    assert scores["teacher"] == 50.0
    assert scores["resources"] is None


@pytest.fixture
def principal_client(client, school):
    user = UserFactory(full_name="المدير")
    MembershipFactory(user=user, school=school, role=RoleFactory(school=school, name="principal"))
    client.force_login(user)
    return client


@pytest.fixture
def tiny_schedule(school):
    from operations.scheduler import generate_schedule

    group = ClassGroupFactory(school=school, grade="G8", level_type="prep", academic_year=YEAR)
    maths = Subject.objects.create(school=school, name_ar="الرياضيات", code="MAT", pedagogy="heavy")
    teacher = UserFactory(full_name="رياضيّ")
    MembershipFactory(user=teacher, school=school, role=RoleFactory(school=school, name="teacher"))
    SubjectClassAssignment.objects.create(
        school=school,
        academic_year=YEAR,
        teacher=teacher,
        class_group=group,
        subject=maths,
        weekly_periods=5,
        is_active=True,
    )
    return generate_schedule(school, YEAR)["generation"]


def test_the_page_shows_gate_radar_and_tiles(principal_client, tiny_schedule):
    body = principal_client.get(
        reverse("schedule_quality_lab") + f"?year={YEAR}", HTTP_HOST="localhost"
    ).content.decode()

    # البوّابةُ شريطُ أرقامٍ من ثلاث بطاقات (`kpi_strip`)، والناجحةُ خضراء.
    assert body.count("data-ui-kpi") == 3 and "ui-kpi kpi-green" in body
    assert 'id="lab-radar"' in body and "lab-radar-data" in body
    assert "الفراغ الزائد عن الاستراحة (متوسّط)" in body and "أشدّ خمسة معلّمين ضغطاً" in body
    assert "الأساس (لا أساس بعد)" in body


def test_saving_a_baseline_from_the_page_and_comparing(principal_client, tiny_schedule, school):
    url = reverse("schedule_quality_lab") + f"?year={YEAR}&schedule=live"
    response = principal_client.post(
        url, {"save_baseline": "1", "label": "أساس الصفحة"}, follow=True, HTTP_HOST="localhost"
    )

    assert response.status_code == 200
    baseline = ScheduleBaseline.objects.get(label="أساس الصفحة")
    assert baseline.metrics["validity.completeness"]["value"] == 100.0
    body = response.content.decode()
    assert "مقابل الأساس «أساس الصفحة»" in body
    assert "lab-bar--ref" in body, "شريطُ المرجع يظهر متى وُجد أساس"
    # الفرقُ بإشارةٍ صريحةٍ ونصٍّ للحكم يقرؤه قارئُ الشاشة (الفرقُ صفرٌ هنا: بلا حكم).
    assert "بلا حكم:" in body


def test_a_generation_can_be_measured_against_the_live_schedule(principal_client, tiny_schedule):
    url = reverse("schedule_quality_lab") + f"?year={YEAR}&schedule={tiny_schedule.id}&ref=live"
    body = principal_client.get(url, HTTP_HOST="localhost").content.decode()

    assert "مقابل الجدول الحيّ" in body
    assert f'value="{tiny_schedule.id}" selected' in body


def _lab_body(client, extra=""):
    return client.get(
        reverse("schedule_quality_lab") + f"?year={YEAR}{extra}", HTTP_HOST="localhost"
    ).content.decode()


def test_bar_widths_are_never_localized(principal_client, tiny_schedule):
    """«83,8%» فاصلةٌ عشريّةٌ محلّيّةٌ تُبطل `width` فتفرغ الشرائط كلُّها (البند 1)."""
    body = _lab_body(principal_client)

    widths = re.findall(r"--progress-w:([^;\"%]*)%", body)
    assert widths, "لا شريطَ في الصفحة"
    assert all("," not in w and "،" not in w for w in widths), widths


def test_hover_only_titles_became_focusable_hints(principal_client, tiny_schedule):
    """صيغةُ الضغط وتفصيلُ المؤشر لا تُحجب خلف `title` وحدَه (D-170): أيقونةُ تلميحٍ تُركَّز."""
    body = _lab_body(principal_client)

    assert 'class="ui-tip__btn" aria-label="صيغة الضغط"' in body
    assert "الضغط = (الفراغ الموزون" in body
    assert 'title="عنّابي' not in body, "وسيلةُ الإيضاح ظاهرةٌ في ذيل البطاقات لا title"
    assert not re.search(r'class="lab-tile"[^>]*title=', body)


def test_tables_have_scoped_headers(principal_client, tiny_schedule):
    body = _lab_body(principal_client)

    assert not [
        t for t in re.findall(r"<th(?:\s[^>]*)?>", body) if "scope=" not in t
    ], "رأسُ جدولٍ بلا scope"


def test_baseline_save_is_a_separate_card_not_inside_the_live_filter_bar(
    principal_client, tiny_schedule
):
    body = _lab_body(principal_client)

    live = re.search(r'<form method="get">.*?</form>', body, re.S).group(0)
    assert "save_baseline" not in live, "شريطُ التصفية الحيّ GET فقط"
    assert body.index("lab-save") > body.index("lab-head"), "الحفظ في بطاقته تحت الشريط"


def test_decorative_bars_are_hidden_from_assistive_tech_and_classes_are_prefixed(
    principal_client, tiny_schedule
):
    body = _lab_body(principal_client)

    assert 'class="lab-tile__bars" aria-hidden="true"' in body
    assert not re.search(r'class="(tile|tiles|delta|legend|bar)[ "]', body)
    main_tag = re.search(r"<main[^>]*>", body).group(0)
    assert "page-noscroll" not in main_tag, "نمطُ الصفحة تقرير: تمريرٌ طبيعيّ لا لوحةٌ بلا تمرير"

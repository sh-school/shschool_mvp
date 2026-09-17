"""بديلُ الجناح يرصد بتكليفه لا بدوره.

قرارُ المدير: البديلُ مشرفٌ إداريٌّ أو ملاحظُ طلبةٍ أو عاملُ خدمات (`SUBSTITUTE_ROLES`).
وكانت شاشةُ التكليف تقبل الثلاثة، والرصدُ ولوحتُه يُفتحان بالدور وحدَه — فلمّا كُلّف
ملاحظُ طلبةٍ بجناح دخل فلقي «لم تُفعَّل صلاحيّاتُك بعد»، وخمسُ شُعبٍ بلا رصد.

فالقدرةُ ``wings.record_day`` تُمنح بالدور **أو** بحمل جناحٍ في اليوم، والقائمةُ
ولوحةُ التحكّم تسألان السؤالَ نفسَه — ومتى انتهى التكليفُ انتهى المنح.
"""

import datetime as dt

import pytest
from django.urls import reverse
from django.utils import timezone

from core.academic_calendar import academic_year_for_school
from core.capabilities import has_capability
from core.models import Wing, WingCoverage
from core.navigation import can_open
from tests.conftest import MembershipFactory, RoleFactory, UserFactory

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def on_a_school_day(monkeypatch):
    """الأربعاءُ صباحاً: يومَ الجمعة لا تُعرض الشُّعب (لا دوام)، فاختبارٌ على الساعة
    الحقيقيّة يسقط آخرَ الأسبوع وحدَه."""
    frozen = timezone.make_aware(dt.datetime(2026, 9, 16, 9, 0))
    monkeypatch.setattr("django.utils.timezone.now", lambda: frozen)


def _staff(school, name, role, national_id):
    user = UserFactory(full_name=name, national_id=national_id)
    MembershipFactory(user=user, school=school, role=RoleFactory(school=school, name=role))
    return user


@pytest.fixture
def wing(school):
    owner = _staff(school, "المشرف الأصيل", "admin_supervisor", "29400000001")
    return Wing.objects.create(
        school=school,
        code="w4",
        name="جناح 4",
        academic_year=academic_year_for_school(school),
        supervisor=owner,
    )


@pytest.fixture
def principal(school):
    return _staff(school, "المدير", "principal", "29400000002")


def _cover(wing, substitute, assigned_by, start, end=None):
    return WingCoverage.objects.create(
        wing=wing, substitute=substitute, assigned_by=assigned_by, start_date=start, end_date=end
    )


@pytest.mark.parametrize("role", ["student_observer", "services_worker"])
def test_a_covering_substitute_may_record(client_as, school, wing, principal, role):
    substitute = _staff(school, "البديل", role, "29400000003")
    today = timezone.localdate()
    _cover(wing, substitute, principal, today)

    assert has_capability(substitute, "wings.record_day")
    assert can_open(substitute, "wings:record_index"), "الرابطُ يُعرض لمن يفتحه"
    response = client_as(substitute).get(reverse("wings:record_index"))
    assert response.status_code == 200
    assert "جناح 4" in response.content.decode()


def test_the_substitutes_dashboard_is_the_wing_not_an_empty_board(
    client_as, school, wing, principal
):
    substitute = _staff(school, "ملاحظ الطلبة", "student_observer", "29400000004")
    _cover(wing, substitute, principal, timezone.localdate())

    body = client_as(substitute).get(reverse("dashboard")).content.decode()

    assert "لم تُفعَّل صلاحيّاتُك" not in body
    assert "رصد الغياب — جناحي اليوم" in body
    assert "جناح 4" in body


def test_the_grant_ends_with_the_cover(client_as, school, wing, principal):
    substitute = _staff(school, "بديلٌ انتهى تكليفه", "student_observer", "29400000005")
    today = timezone.localdate()
    _cover(wing, substitute, principal, today - dt.timedelta(days=5), today - dt.timedelta(days=1))

    assert not has_capability(substitute, "wings.record_day")
    assert not can_open(substitute, "wings:record_index")
    assert client_as(substitute).get(reverse("wings:record_index")).status_code in (302, 403)
    body = client_as(substitute).get(reverse("dashboard")).content.decode()
    assert "لم تُفعَّل صلاحيّاتُك" in body


def test_the_substitute_opens_no_other_wing_screen(client_as, school, wing, principal):
    """البوّابةُ تُدخل أدوارَ البديل، وكلُّ شاشةٍ تقرّر بحارسها: الرصدُ بالتكليف، والبقيّةُ لا."""
    substitute = _staff(school, "البديل", "services_worker", "29400000008")
    _cover(wing, substitute, principal, timezone.localdate())
    client = client_as(substitute)

    assert client.get(reverse("wings:floors")).status_code in (302, 403)
    assert client.get(reverse("wings:coverage")).status_code in (302, 403)
    assert not can_open(substitute, "wings:floors")


def test_an_uncovered_observer_is_still_refused(client_as, school, wing):
    observer = _staff(school, "ملاحظٌ بلا تكليف", "student_observer", "29400000006")

    assert not Wing.is_held_by(observer)
    assert client_as(observer).get(reverse("wings:record_index")).status_code in (302, 403)


def test_the_owner_does_not_hold_a_covered_wing(school, wing, principal):
    substitute = _staff(school, "البديل", "student_observer", "29400000007")
    _cover(wing, substitute, principal, timezone.localdate())

    assert not Wing.is_held_by(wing.supervisor)
    assert Wing.is_held_by(substitute)


def test_the_dashboard_uses_the_schools_day_not_utc(client_as, school, wing, principal, settings):
    """21:30 UTC = 00:30 بتوقيت قطر: تكليفٌ يبدأ «اليوم» بتوقيت المدرسة يجب أن تراه اللوحة.

    سقطت البوّابةُ على `main` عند منتصف الليل (2026-09-14) لأنّ اللوحةَ كانت تقرأ
    `timezone.now().date()` (UTC) والتكليفُ بـ`localdate()` (قطر).
    """
    import datetime as dt
    from unittest import mock

    from django.utils import timezone as tz

    frozen = dt.datetime(2026, 9, 13, 21, 30, tzinfo=dt.UTC)  # 00:30 بتوقيت قطر، 2026-09-14
    substitute = _staff(school, "بديلُ منتصف الليل", "student_observer", "29400000009")
    with mock.patch("django.utils.timezone.now", return_value=frozen):
        _cover(wing, substitute, principal, tz.localdate())
        assert tz.localdate() == dt.date(2026, 9, 14)
        body = client_as(substitute).get(reverse("dashboard")).content.decode()

    assert "رصد الغياب — جناحي اليوم" in body
    assert "لم تُفعَّل صلاحيّاتُك" not in body

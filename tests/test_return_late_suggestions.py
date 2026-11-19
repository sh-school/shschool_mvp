"""إدارةُ الأجنحة 4/4 (W-20261119-004): التقريرُ الأسبوعيّ للنائب واقتراحُ متابعة تأخّر العودة.

[LEGAL] لا نصَّ لائحيَّ يحدّد الحدَّ؛ هو قرارُ مالكٍ (2026-11-19): 30 دقيقةً في الأسبوع قابلةً للضبط، والمتجاوزُ
يُقترح لمشرف جناحه فقط، والقرارُ له قبولاً أو رفضاً بلا مخالفةٍ آليّة، والموسومُ بخروجٍ مبرَّر لا يُقترح له ولا يظهر.
المصدر: AAdocs/ministry_data/2026_2027/08_conduct_policy_2026.md م3.4.3
"""

import pytest
from django.test import override_settings
from django.urls import reverse
from django.utils import timezone

from behavior.models import BehaviorInfraction
from operations import exit_wing
from operations.models import ClassExit
from student_affairs.movement_selectors import weekly_report
from tests.test_movement_live import _exit, wing_a, wing_b  # noqa: F401
from wings import return_late_services as service
from wings.conduct_beat import conduct_proposals_beat
from wings.models import ReturnLateSuggestion
from wings.scope import StudentScope

pytestmark = [pytest.mark.django_db, pytest.mark.pin_clock]


def _late(card: ClassExit, minutes: int) -> ClassExit:
    ClassExit.objects.filter(pk=card.pk).update(late_return_seconds=minutes * 60)
    return card


def _scope(school, klass) -> StudentScope:
    return StudentScope(school, frozenset({klass.wing_id}), klass.academic_year)


def test_31_minutes_in_the_week_gives_one_suggestion_at_the_wing_supervisor(
    school, teacher_user, wing_a, wing_b
):
    klass, sup = wing_a
    other_klass, _ = wing_b
    _late(_exit(school, klass, teacher_user, "متأخر", "29000000701", back_after=40), 31)

    stats = service.generate_for_week(school, timezone.localdate())

    assert stats["created"] == 1
    suggestion = ReturnLateSuggestion.objects.get()
    assert (suggestion.late_minutes, suggestion.status) == (31, "proposed")
    assert [s.pk for s in service.queue_for(school, _scope(school, klass))] == [suggestion.pk]
    assert service.queue_for(school, _scope(school, other_klass)) == []


def test_running_the_job_twice_does_not_repeat_the_suggestion(school, teacher_user, wing_a):
    klass, sup = wing_a
    _late(_exit(school, klass, teacher_user, "متأخر", "29000000702", back_after=40), 45)
    today = timezone.localdate()

    first = service.generate_for_week(school, today)
    second = service.generate_for_week(school, today)

    assert first["created"] == 1 and second == {"created": 0, "updated": 0, "withdrawn": 0}
    assert ReturnLateSuggestion.objects.count() == 1


def test_exactly_the_threshold_is_not_over_it_and_the_threshold_is_configurable(
    school, teacher_user, wing_a
):
    klass, _ = wing_a
    _late(_exit(school, klass, teacher_user, "حدّي", "29000000703", back_after=40), 30)

    assert service.generate_for_week(school, timezone.localdate())["created"] == 0
    with override_settings(WING_RETURN_LATE_THRESHOLD_MINUTES=20):
        assert service.generate_for_week(school, timezone.localdate())["created"] == 1


def test_excused_student_is_neither_suggested_nor_in_the_report(
    school, teacher_user, nurse_user, wing_a
):
    klass, _ = wing_a
    card = _late(_exit(school, klass, teacher_user, "موسوم", "29000000704", back_after=40), 90)
    day = timezone.localdate()
    exit_wing.set_excused(school, card.student, nurse_user, day, "سبب", starts_on=day)

    assert service.generate_for_week(school, day)["created"] == 0
    assert weekly_report(school, StudentScope(school, None), exit_wing.week_start_of(day)) == []


def test_the_suggestion_is_withdrawn_when_a_mark_makes_it_stale(
    school, teacher_user, nurse_user, wing_a
):
    klass, _ = wing_a
    card = _late(_exit(school, klass, teacher_user, "ثم وُسم", "29000000705", back_after=40), 60)
    day = timezone.localdate()
    service.generate_for_week(school, day)
    exit_wing.set_excused(school, card.student, nurse_user, day, "سبب", starts_on=day)

    assert service.generate_for_week(school, day)["withdrawn"] == 1
    assert ReturnLateSuggestion.objects.get().status == "withdrawn"


def test_supervisor_decides_without_any_automatic_infraction_and_only_in_own_wing(
    school, teacher_user, wing_a, wing_b
):
    klass, sup = wing_a
    _, other_sup = wing_b
    _late(_exit(school, klass, teacher_user, "متأخر", "29000000706", back_after=40), 50)
    service.generate_for_week(school, timezone.localdate())
    pk = ReturnLateSuggestion.objects.get().pk

    with pytest.raises(service.SuggestionError):
        service.accept(pk, other_sup, _scope(school, wing_b[0]))
    done = service.accept(pk, sup, _scope(school, klass))

    assert (done.status, done.decided_by) == ("accepted", sup)
    assert BehaviorInfraction.objects.count() == 0
    with pytest.raises(service.SuggestionError):
        service.dismiss(pk, sup, _scope(school, klass))
    # التوليدُ بعد القرار لا يُنشئ بديلاً ولا يمسّ المقرَّر.
    assert service.generate_for_week(school, timezone.localdate())["created"] == 0
    assert ReturnLateSuggestion.objects.get().status == "accepted"


def test_weekly_report_is_per_wing_ordered_by_late_minutes_and_page_opens_for_leadership(
    client, school, principal_user, teacher_user, wing_a, wing_b
):
    _late(_exit(school, wing_a[0], teacher_user, "الأقل", "29000000707", back_after=5), 4)
    _late(_exit(school, wing_a[0], teacher_user, "الأكثر", "29000000708", back_after=5), 25)
    _exit(school, wing_b[0], teacher_user, "ب", "29000000709", back_after=5)

    report = weekly_report(
        school, StudentScope(school, None), exit_wing.week_start_of(timezone.localdate())
    )
    assert [b["wing"] for b in report] == ["wa", "wb"]
    assert [r.student_name for r in report[0]["rows"]] == ["الأكثر", "الأقل"]

    client.force_login(principal_user)
    html = client.get(reverse("student_affairs:movements_weekly")).content.decode()
    assert "الأكثر" in html and "للمتابعة لا للعقوبة" in html


def test_beat_entry_exists_only_when_enabled_and_week_starts_on_sunday():
    assert conduct_proposals_beat({}) == {}
    entry = conduct_proposals_beat({"CONDUCT_PROPOSALS_BEAT": "1"})
    assert entry["generate-return-late-suggestions"]["task"] == (
        "wings.generate_return_late_suggestions"
    )
    import datetime as dt

    assert exit_wing.week_start_of(dt.date(2026, 11, 19)) == dt.date(2026, 11, 15)  # الخميس → أحدُه

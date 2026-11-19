"""بطاقةُ الخروج 3/4 (W-20261119-003): شريطُ الأجنحة، ولحظتا العيادة، والخروجُ المبرَّر، والعدّادان بحسب من يراهما.

[LEGAL] لا نصَّ لائحيَّ يحدّد هذه الأرقامَ؛ هي قراراتُ مالكٍ (2026-11-19) تُثبَّت هنا: المشرفُ لا يرى سببَ زيارة العيادة
ولا سببَ الوسم، والموسومُ لا يُحسب عليه تأخّر، ولا يصل العدّادان إلى وليّ الأمر.
المصدر: AAdocs/ministry_data/2026_2027/08_conduct_policy_2026.md م3.4.3
"""

import datetime as dt

import pytest
from django.urls import reverse
from django.utils import timezone

from clinic.models import ClinicVisit
from operations import exit_card, exit_wing
from operations.models import ClassExit, ExcusedExit, Session, Subject
from student_affairs.movement_strip_selectors import MERGED_LABEL, destination_split, wing_strip
from tests.conftest import UserFactory
from tests.test_movement_live import _exit, _wing, wing_a, wing_b  # noqa: F401
from wings.scope import StudentScope

pytestmark = [pytest.mark.django_db, pytest.mark.pin_clock]

SECRET_REASON = "نوبات ربوٍ شديدة"


def _cap_marks(client, user, name="student_affairs:movements_live"):
    client.force_login(user)
    return client.get(reverse(name)).content.decode()


def _late_card(school, klass, teacher, sup, nid, name="طالب متأخر"):
    """بطاقةٌ لطالبٍ وصل دورةَ المياه قبل 12 دقيقة بمهلة 7 فعاد الآن: متأخّرٌ 5 دقائق (300 ثانية)."""
    exit_card.set_grace(school, "restroom", 7, sup)
    card = _exit(school, klass, teacher, name, nid, dest="wing_sup", minutes_ago=15)
    now = timezone.now()
    exit_card.route(card, "restroom", sup, now=now - dt.timedelta(minutes=12))
    return card, now


# ── شريط الأجنحة ────────────────────────────────────────────────────────────


def test_wing_strip_has_five_cells_per_wing_and_a_total_row(school, teacher_user, wing_a, wing_b):
    klass_a, sup_a = wing_a
    klass_b, _ = wing_b
    now = timezone.now()
    out = _exit(school, klass_a, teacher_user, "خارج", "29000000601", dest="restroom")
    ClassExit.objects.filter(pk=out.pk).update(routed_at=out.left_at, allowed_minutes=2)
    _exit(school, klass_a, teacher_user, "لم يُستلم", "29000000602", dest="wing_sup")
    _exit(school, klass_b, teacher_user, "عاد", "29000000603", back_after=3)

    rows = wing_strip(school, StudentScope(school, None), timezone.localdate(now), now)
    by_name = {r["wing"]: dict(r["cells"]) for r in rows}

    assert [r["wing"] for r in rows][0] == "كلّ الأجنحة" and len(rows) == 3
    assert all(len(r["cells"]) == 5 for r in rows)
    assert by_name["wa"]["خارج الآن"] == 1 and by_name["wa"]["متأخر"] == 1
    assert by_name["wa"]["لم يُستلم"] == 1 and by_name["wb"]["عادوا اليوم"] == 1
    assert by_name["كلّ الأجنحة"]["خارج الآن"] == 1


def test_strip_is_on_the_live_panel_for_leadership(
    client, school, principal_user, teacher_user, wing_a
):
    _exit(school, wing_a[0], teacher_user, "طالب", "29000000611")

    html = _cap_marks(client, principal_user)

    assert "الأجنحة الآن" in html and "عادوا متأخرين" in html and "لم يُستلم" in html


def test_destination_split_merges_clinic_for_non_health_viewers(school, teacher_user, wing_a):
    klass, _ = wing_a
    _exit(school, klass, teacher_user, "ط1", "29000000621", dest="clinic")
    _exit(school, klass, teacher_user, "ط2", "29000000622", dest="restroom")
    day = timezone.localdate()
    scope = StudentScope(school, None)

    general = dict(destination_split(school, scope, day, health_viewer=False))
    health = dict(destination_split(school, scope, day, health_viewer=True))

    assert "العيادة" not in general and general[MERGED_LABEL] == 1 and general["دورة المياه"] == 1
    assert health["العيادة"] == 1


# ── لحظتا العيادة ───────────────────────────────────────────────────────────


def test_nurse_presses_arrive_then_depart_once_and_supervisor_sees_no_reason(
    client, school, nurse_user, teacher_user, wing_a
):
    klass, sup = wing_a
    card = _exit(school, klass, teacher_user, "طالب العيادة", "29000000631", dest="clinic")
    ClinicVisit.objects.create(
        school=school, student=card.student, nurse=nurse_user, reason=SECRET_REASON
    )
    client.force_login(nurse_user)
    arrive = reverse("clinic:exit_card_moment", args=[card.pk, "arrive"])
    depart = reverse("clinic:exit_card_moment", args=[card.pk, "depart"])

    assert client.post(depart).status_code == 302  # لا مغادرةَ قبل الوصول
    card.refresh_from_db()
    assert card.clinic_left_at is None
    client.post(arrive)
    first = ClassExit.objects.get(pk=card.pk).clinic_arrived_at
    client.post(arrive)  # الثانيةُ لا تفعل شيئاً
    assert ClassExit.objects.get(pk=card.pk).clinic_arrived_at == first
    client.post(depart)
    card.refresh_from_db()
    assert card.clinic_arrived_at is not None and card.clinic_left_at is not None
    assert card.returned_at is None  # المغادرةُ لا تُعيد الطالبَ إلى فصله

    html = _cap_marks(client, sup)
    assert "وصل" in html and "غادر" in html
    assert SECRET_REASON not in html and "ربو" not in html


def test_only_the_nurse_presses_clinic_moments(client, school, teacher_user, wing_a):
    klass, sup = wing_a
    card = _exit(school, klass, teacher_user, "ط", "29000000641", dest="clinic")
    for user in (teacher_user, sup):
        client.force_login(user)
        resp = client.post(reverse("clinic:exit_card_moment", args=[card.pk, "arrive"]))
        assert resp.status_code in (302, 403)
    assert ClassExit.objects.get(pk=card.pk).clinic_arrived_at is None


# ── الخروج المبرَّر الدائم ───────────────────────────────────────────────────


def test_excused_student_gets_no_late_return_and_counts_none(
    school, nurse_user, teacher_user, wing_a
):
    klass, sup = wing_a
    card, now = _late_card(school, klass, teacher_user, sup, "29000000651")
    day = timezone.localdate(now)
    exit_wing.set_excused(school, card.student, nurse_user, day + dt.timedelta(days=30), "ربو")

    done, _ = exit_card.return_exit(card.pk, sup, now=now)

    assert done is not None and done.late_return_seconds is None
    assert (
        exit_wing.exit_counters(school, [card.student_id], day)[card.student_id].late_minutes == 0
    )


def test_a_non_excused_student_is_late_and_the_counter_shows_minutes(school, teacher_user, wing_a):
    klass, sup = wing_a
    card, now = _late_card(school, klass, teacher_user, sup, "29000000652")

    done, _ = exit_card.return_exit(card.pk, sup, now=now)

    assert done is not None and done.late_return_seconds == 300
    counter = exit_wing.exit_counters(school, [card.student_id], timezone.localdate(now))[
        card.student_id
    ]
    assert (counter.count, counter.late_minutes) == (1, 5)


def test_mark_set_after_the_return_drops_the_late_from_the_counters(
    school, nurse_user, teacher_user, wing_a
):
    klass, sup = wing_a
    card, now = _late_card(school, klass, teacher_user, sup, "29000000653")
    exit_card.return_exit(card.pk, sup, now=now)
    day = timezone.localdate(now)
    exit_wing.set_excused(school, card.student, nurse_user, day, "ربو", starts_on=day)

    assert (
        exit_wing.exit_counters(school, [card.student_id], day)[card.student_id].late_minutes == 0
    )


def test_supervisor_sees_the_mark_but_never_its_reason(
    client, school, nurse_user, teacher_user, wing_a
):
    klass, sup = wing_a
    card = _exit(school, klass, teacher_user, "موسوم", "29000000661", dest="restroom")
    ClassExit.objects.filter(pk=card.pk).update(routed_at=card.left_at, allowed_minutes=1)
    exit_wing.set_excused(school, card.student, nurse_user, timezone.localdate(), SECRET_REASON)

    live = _cap_marks(client, sup)
    history = _cap_marks(client, sup, "student_affairs:movements_history")

    assert "خروج مبرَّر" in live and "status-danger" not in live
    assert SECRET_REASON not in live and SECRET_REASON not in history
    assert ExcusedExit.objects.get().reason == SECRET_REASON


def test_excuse_is_for_nurse_and_specialists_only_with_a_bounded_written_reason(
    school, nurse_user, teacher_user, social_worker_user, psychologist_user, wing_a
):
    student = UserFactory(full_name="طالب", national_id="29000000671")
    day = timezone.localdate()

    with pytest.raises(PermissionError):
        exit_wing.set_excused(school, student, teacher_user, day, "سبب")
    with pytest.raises(ValueError, match="سبب"):
        exit_wing.set_excused(school, student, nurse_user, day, "  ")
    with pytest.raises(ValueError, match="قبل"):
        exit_wing.set_excused(school, student, nurse_user, day - dt.timedelta(days=1), "س")
    with pytest.raises(ValueError, match="عام"):
        exit_wing.set_excused(school, student, nurse_user, day + dt.timedelta(days=400), "س")
    for who in (social_worker_user, psychologist_user):
        assert exit_wing.set_excused(school, student, who, day, "س").set_by == who


def test_excuse_endpoint_is_closed_to_teacher_and_guardian_and_audit_has_no_reason(
    client, school, nurse_user, teacher_user, parent_user, student_user, wing_a
):
    from core.models import AuditLog
    from tests.conftest import StudentEnrollmentFactory

    StudentEnrollmentFactory(student=student_user, class_group=wing_a[0])
    url = reverse("clinic:exit_card_excuse")
    ends = (timezone.localdate() + dt.timedelta(days=5)).isoformat()
    body = {"student": str(student_user.pk), "ends_on": ends, "reason": SECRET_REASON}

    for user in (teacher_user, parent_user):
        client.force_login(user)
        assert client.post(url, body).status_code in (302, 403)
    assert not ExcusedExit.objects.exists()

    client.force_login(nurse_user)
    client.post(url, body)
    assert ExcusedExit.objects.count() == 1
    logged = " ".join(str(a.changes) + a.object_repr for a in AuditLog.objects.all())
    assert SECRET_REASON not in logged


def test_excuse_for_a_student_of_another_school_is_refused(client, nurse_user, db):
    stranger = UserFactory(full_name="غريب", national_id="29000000681")
    client.force_login(nurse_user)
    client.post(
        reverse("clinic:exit_card_excuse"),
        {"student": str(stranger.pk), "ends_on": "2099-01-01", "reason": "س"},
    )
    assert not ExcusedExit.objects.exists()


# ── العدّادان: بالمادّة، ولا يصلان لوليّ الأمر ───────────────────────────────


def test_teacher_counters_cover_only_his_subject(school, teacher_user, wing_a):
    klass, _ = wing_a
    math = Subject.objects.create(school=school, name_ar="رياضيات", code="MTH")
    sci = Subject.objects.create(school=school, name_ar="علوم", code="SCI")
    mine = _exit(school, klass, teacher_user, "طالبي", "29000000691", back_after=10, minutes_ago=30)
    Session.objects.filter(pk=mine.session_id).update(subject=math)
    other = Session.objects.create(
        school=school,
        class_group=klass,
        teacher=teacher_user,
        subject=sci,
        date=timezone.localdate(),
        start_time=dt.time(7, 0),
        end_time=dt.time(7, 40),
        status="scheduled",
    )
    left = timezone.now() - dt.timedelta(minutes=90)
    ClassExit.objects.create(
        school=school,
        session=other,
        student=mine.student,
        destination="restroom",
        left_at=left,
        returned_at=left + dt.timedelta(minutes=20),
    )
    day = timezone.localdate()

    only_math = exit_wing.exit_counters(school, [mine.student_id], day, subject_ids=[math.pk])
    everything = exit_wing.exit_counters(school, [mine.student_id], day)

    assert only_math[mine.student_id].minutes == 10 and only_math[mine.student_id].count == 1
    assert everything[mine.student_id].minutes == 30 and everything[mine.student_id].count == 2


def test_grid_counters_are_empty_for_a_teacher_with_no_subject_in_the_class(
    school, teacher_user, wing_a
):
    klass, _ = wing_a
    card = _exit(school, klass, teacher_user, "ط", "29000000692", back_after=4)

    got = exit_wing.grid_counters(
        school, klass, [card.student_id], timezone.localdate(), teacher=teacher_user
    )

    assert got == {}


def test_guardian_cannot_open_the_counters_screens(client, parent_user):
    client.force_login(parent_user)
    for name in ("student_affairs:movements_history", "student_affairs:movements_live"):
        assert client.get(reverse(name)).status_code in (302, 403)


def test_clinic_exit_page_shows_arrive_button_to_the_nurse_and_is_closed_to_teachers(
    client, school, nurse_user, teacher_user, wing_a
):
    klass, _ = wing_a
    _exit(school, klass, teacher_user, "طالب العيادة", "29000000701", dest="clinic")
    url = reverse("clinic:exit_card")

    client.force_login(nurse_user)
    html = client.get(url).content.decode()
    assert "وصل العيادة" in html and "طالب العيادة" in html

    client.force_login(teacher_user)
    assert client.get(url).status_code in (302, 403)

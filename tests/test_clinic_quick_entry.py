"""
tests/test_clinic_quick_entry.py — الإدخال السريع وطابور العيادة (W-20261020-030)

الطابور بثلاث حالات، والإغلاق التلقائي بعد ثلاث ساعات، وثباتُ عدد الاستعلامات، وحدودُ الصلاحية،
والأزرارُ ≥ 3rem، ولا تخزينَ للصفحات.
"""

import datetime as dt
import pathlib
import re

import pytest
from django.db import connection
from django.test import Client
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

from clinic import choices
from clinic.models import ClinicVisit
from clinic.queue import todays_queue, visit_state
from clinic.services import ClinicService

ROOT = pathlib.Path(__file__).resolve().parent.parent


def _client(user):
    c = Client()
    c.force_login(user)
    return c


pytestmark = pytest.mark.pin_clock


@pytest.mark.django_db
def test_queue_has_three_states_derived_from_the_coded_fields(school, nurse_user, student_user):
    v = ClinicService.start_visit(school, student_user, nurse_user)
    assert visit_state(v) == choices.STATE_WAITING
    ClinicService.set_coding(v, service_code="bandage")
    assert visit_state(v) == choices.STATE_IN_CARE
    ClinicService.close_visit(v, choices.OUTCOME_RETURN)
    assert visit_state(v) == choices.STATE_DONE
    queue = todays_queue(school, timezone.localdate())
    assert [x.pk for x in queue.done] == [v.pk] and not queue.waiting and not queue.in_care


@pytest.mark.django_db
def test_starting_twice_reuses_the_open_visit(school, nurse_user, student_user):
    first = ClinicService.start_visit(school, student_user, nurse_user)
    again = ClinicService.start_visit(school, student_user, nurse_user)
    assert first.pk == again.pk and ClinicVisit.objects.count() == 1


@pytest.mark.django_db
def test_stale_visits_close_after_three_hours_and_only_once(school, nurse_user, student_user):
    old = ClinicService.start_visit(school, student_user, nurse_user)
    ClinicVisit.objects.filter(pk=old.pk).update(
        visit_date=timezone.now() - dt.timedelta(hours=3, minutes=5)
    )
    fresh_student = student_user.__class__.objects.create(
        full_name="طالب ثانٍ", national_id="29999999999"
    )
    fresh = ClinicVisit.objects.create(
        school=school, student=fresh_student, nurse=nurse_user, reason=""
    )
    assert ClinicService.auto_close_stale(school) == 1
    old.refresh_from_db()
    fresh.refresh_from_db()
    assert old.outcome == choices.OUTCOME_AUTO and old.closed_at is not None
    # المدّة = المهلة نفسها لا لحظة التشغيل
    assert old.duration_seconds == 3 * 3600
    assert fresh.closed_at is None
    assert ClinicService.auto_close_stale(school) == 0
    day = timezone.localtime(old.visit_date).date()
    assert [v.pk for v in todays_queue(school, day).auto_closed] == [old.pk]


@pytest.mark.django_db
def test_queue_query_count_does_not_grow_with_rows(school, nurse_user, django_user_model):
    def add(n):
        for i in range(n):
            s = django_user_model.objects.create(
                full_name=f"طالب {i}-{timezone.now().timestamp()}", national_id=f"2{i:010d}{n}"
            )
            ClinicVisit.objects.create(school=school, student=s, nurse=nurse_user, reason="")

    add(2)
    with CaptureQueriesContext(connection) as small:
        todays_queue(school, timezone.localdate())
    add(10)
    with CaptureQueriesContext(connection) as large:
        todays_queue(school, timezone.localdate())
    assert len(large) == len(small) == 1


@pytest.mark.django_db
def test_quick_screens_need_the_nurse_capability(school, teacher_user):
    resp = _client(teacher_user).get(reverse("clinic:quick_entry"))
    assert resp.status_code in (302, 403)
    resp = _client(teacher_user).post(reverse("clinic:quick_start"), {"student_id": "x"})
    assert resp.status_code in (302, 403)


@pytest.mark.django_db
def test_nurse_flow_search_start_service_close(school, nurse_user, student_user):
    c = _client(nurse_user)
    page = c.get(reverse("clinic:quick_entry"))
    assert page.status_code == 200 and "no-store" in page["Cache-Control"]

    found = c.get(reverse("clinic:quick_search"), {"q": student_user.full_name[:3]})
    assert found.status_code == 200 and student_user.full_name in found.content.decode()
    assert c.get(reverse("clinic:quick_search"), {"q": "ط"}).content.decode().strip() == ""

    started = c.post(reverse("clinic:quick_start"), {"student_id": str(student_user.id)})
    assert started.status_code == 200 and "clinic-visit-changed" in started["HX-Trigger"]
    assert 'id="quick-results" hx-swap-oob="true"' in started.content.decode()
    visit = ClinicVisit.objects.get()

    ok = c.post(
        reverse("clinic:quick_service", args=[visit.id]),
        {"service_code": "ors", "complaint_code": "nausea_vomiting"},
    )
    assert ok.status_code == 200
    visit.refresh_from_db()
    assert (visit.service_code, visit.service_group) == ("ors", choices.GROUP_MEDICATION)

    bad = c.post(reverse("clinic:quick_service", args=[visit.id]), {"service_code": "nope"})
    assert bad.status_code == 400

    done = c.post(reverse("clinic:quick_close", args=[visit.id]), {"outcome": "sent_home"})
    assert done.status_code == 200
    visit.refresh_from_db()
    assert visit.outcome == choices.OUTCOME_LEAVE and visit.closed_at is not None
    assert (
        c.post(reverse("clinic:quick_close", args=[visit.id]), {"outcome": "referral"}).status_code
        == 400
    )


@pytest.mark.django_db
def test_a_visit_of_another_school_is_not_reachable(school, nurse_user, student_user):
    from tests.conftest import SchoolFactory

    other = SchoolFactory()
    stranger = ClinicVisit.objects.create(school=other, student=student_user, reason="")
    resp = _client(nurse_user).post(
        reverse("clinic:quick_close", args=[stranger.id]), {"outcome": "return_to_class"}
    )
    assert resp.status_code == 404


def test_tap_targets_are_at_least_three_rem_and_templates_use_them():
    css = (ROOT / "static" / "css" / "custom" / "33-modules-4.css").read_text(encoding="utf-8")
    rule = re.search(r"\.clinic-tap\s*\{([^}]*)\}", css).group(1)
    assert "min-block-size: 3rem" in rule and "min-inline-size: 3rem" in rule
    panel = (ROOT / "templates" / "clinic" / "partials" / "_quick_panel.html").read_text(
        encoding="utf-8"
    )
    assert panel.count("clinic-tap") >= 3


def test_the_auto_close_beat_is_off_unless_explicitly_enabled():
    from clinic.autoclose_beat import clinic_autoclose_beat

    assert clinic_autoclose_beat({}) == {}
    assert "clinic-auto-close-stale-visits" in clinic_autoclose_beat({"CLINIC_AUTOCLOSE_BEAT": "1"})


@pytest.mark.django_db
def test_full_form_rejects_an_unapproved_code_with_400_not_500(school, nurse_user, student_user):
    resp = _client(nurse_user).post(
        reverse("clinic:record_visit"),
        {"student_id": str(student_user.id), "reason": "x", "service_code": "bogus"},
    )
    assert resp.status_code == 400 and not ClinicVisit.objects.exists()


def test_admin_hides_the_service_group_from_lists():
    from clinic.admin import ClinicVisitAdmin

    assert "service_group" not in ClinicVisitAdmin.list_display
    assert "service_group" not in ClinicVisitAdmin.list_filter


@pytest.mark.django_db
def test_quick_start_refuses_an_inactive_or_foreign_student(school, nurse_user):
    from tests.conftest import MembershipFactory, RoleFactory, SchoolFactory, UserFactory

    role = RoleFactory(school=school, name="student")
    inactive = UserFactory(full_name="طالب منقطع")
    MembershipFactory(user=inactive, school=school, role=role, is_active=False)

    other = SchoolFactory()
    other_role = RoleFactory(school=other, name="student")
    foreign = UserFactory(full_name="طالب مدرسة أخرى")
    MembershipFactory(user=foreign, school=other, role=other_role, is_active=True)

    c = _client(nurse_user)
    for student in (inactive, foreign):
        resp = c.post(reverse("clinic:quick_start"), {"student_id": str(student.id)})
        assert resp.status_code == 404
    assert not ClinicVisit.objects.exists()


# ── W-20261124-009: «قادمون إليك» بزر استلام واحد، وإغلاق الزيارة يسجّل «غادر» ──
from operations.models import ClassExit  # noqa: E402
from tests.test_movement_live import _exit, wing_a  # noqa: E402,F401


def _quick_html(client, user):
    client.force_login(user)
    return client.get(reverse("clinic:quick_entry")).content.decode()


@pytest.mark.django_db
def test_incoming_lists_unreceived_clinic_exits_with_counter_and_wait(
    client, school, nurse_user, teacher_user, wing_a
):
    klass, _ = wing_a
    _exit(school, klass, teacher_user, "طالب قادم", "29000000021", minutes_ago=7)
    done = _exit(school, klass, teacher_user, "طالب مستلم", "29000000022")
    ClassExit.objects.filter(pk=done.pk).update(clinic_arrived_at=timezone.now())
    _exit(school, klass, teacher_user, "طالب مشرف", "29000000023", dest="wing_sup")

    html = _quick_html(client, nurse_user)

    block = html.split("قادمون إليك")[1].split("الإدخال السريع")[0]
    assert "طالب قادم" in block and "طالب مستلم" not in block and "طالب مشرف" not in html
    assert "data-quiet-poll" in html and "every 20s" in html
    assert reverse("clinic:quick_incoming") in html
    assert client.get(reverse("clinic:quick_incoming")).status_code == 200


@pytest.mark.django_db
def test_receive_records_arrival_starts_visit_and_is_idempotent(
    client, school, nurse_user, teacher_user, wing_a
):
    klass, _ = wing_a
    row = _exit(school, klass, teacher_user, "طالب استلام", "29000000031")
    client.force_login(nurse_user)
    url = reverse("clinic:quick_receive")

    first = client.post(url, {"exit_id": str(row.pk)})
    arrived = ClassExit.objects.get(pk=row.pk).clinic_arrived_at
    second = client.post(url, {"exit_id": str(row.pk)})

    assert first.status_code == second.status_code == 200
    assert "clinic-visit-changed" in first["HX-Trigger"]
    assert arrived is not None and ClassExit.objects.get(pk=row.pk).clinic_arrived_at == arrived
    assert ClinicVisit.objects.count() == 1
    assert ClinicVisit.objects.get().student_id == row.student_id


@pytest.mark.django_db
def test_receive_of_foreign_or_non_clinic_exit_is_404(
    client, school, nurse_user, teacher_user, wing_a
):
    from tests.conftest import SchoolFactory

    klass, _ = wing_a
    wing_row = _exit(school, klass, teacher_user, "طالب جناح", "29000000041", dest="wing_sup")
    foreign = _exit(school, klass, teacher_user, "طالب غريب", "29000000042")
    ClassExit.objects.filter(pk=foreign.pk).update(school=SchoolFactory())
    client.force_login(nurse_user)
    url = reverse("clinic:quick_receive")

    assert client.post(url, {"exit_id": str(wing_row.pk)}).status_code == 404
    assert client.post(url, {"exit_id": str(foreign.pk)}).status_code == 404
    assert client.post(url, {"exit_id": "not-a-uuid"}).status_code == 404
    assert not ClinicVisit.objects.exists()


@pytest.mark.django_db
def test_closing_the_visit_records_departure_but_never_returned_at(
    client, school, nurse_user, teacher_user, wing_a
):
    klass, _ = wing_a
    row = _exit(school, klass, teacher_user, "طالب مغادرة", "29000000051")
    client.force_login(nurse_user)
    client.post(reverse("clinic:quick_receive"), {"exit_id": str(row.pk)})
    visit = ClinicVisit.objects.get()

    client.post(reverse("clinic:quick_close", args=[visit.id]), {"outcome": "sent_home"})

    row.refresh_from_db()
    assert row.clinic_arrived_at is not None and row.clinic_left_at is not None
    assert row.returned_at is None


@pytest.mark.django_db
def test_closing_a_visit_without_arrival_leaves_the_exit_untouched(
    client, school, nurse_user, teacher_user, wing_a
):
    klass, _ = wing_a
    row = _exit(school, klass, teacher_user, "طالب بلا وصول", "29000000061")
    client.force_login(nurse_user)
    # طالبُ المساعد بلا عضويّة دور طالب فمسار quick_start يردّ 404؛ نبدأ الزيارةَ بالخدمة مباشرةً
    visit = ClinicService.start_visit(school, row.student, nurse_user)

    done = client.post(reverse("clinic:quick_close", args=[visit.id]), {"outcome": "sent_home"})

    row.refresh_from_db()
    assert done.status_code == 200
    assert row.clinic_left_at is None and row.returned_at is None


@pytest.mark.django_db
def test_incoming_needs_the_nurse_capability(client, school, teacher_user):
    client.force_login(teacher_user)
    assert client.get(reverse("clinic:quick_incoming")).status_code in (302, 403)
    assert client.post(reverse("clinic:quick_receive"), {"exit_id": "x"}).status_code in (302, 403)


def test_quiet_live_script_is_loaded_and_holds_polls_during_interaction():
    page = (ROOT / "templates" / "clinic" / "quick_entry.html").read_text(encoding="utf-8")
    js = (ROOT / "static" / "js" / "clinic-quick-live.js").read_text(encoding="utf-8")
    assert "clinic-quick-live.js" in page and page.count("data-quiet-poll") == 2
    assert "htmx:beforeRequest" in js and "htmx:beforeSwap" in js and "document.hidden" in js

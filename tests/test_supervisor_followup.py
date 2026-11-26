"""متابعةُ أداء المشرف الإداريّ — نموذج 19 (W-20261125-003)."""

import datetime as dt
import pathlib
import uuid

import pytest
from django.core.management import call_command
from django.urls import reverse
from django.utils import timezone

from core.models import AuditLog
from notifications.models import InAppNotification
from quality.models import (
    SupervisorFollowUp,
    SupervisorFollowUpRecommendation,
    SupervisorFollowUpScore,
)
from quality.supervisor_followup_indicators import INDICATORS, RATINGS
from staff_affairs.models import LeaveRequest, PermitRequest, StaffAttendance
from tests.conftest import MembershipFactory, RoleFactory, SchoolFactory, UserFactory

pytestmark = [pytest.mark.django_db, pytest.mark.pin_clock]

STRENGTH = "نصٌّ حرٌّ عن الالتزام"


def _member(school, role, name):
    user = UserFactory(full_name=name)
    MembershipFactory(user=user, school=school, role=RoleFactory(school=school, name=role))
    return user


@pytest.fixture
def supervisor(school):
    return _member(school, "admin_supervisor", "مشرف اختباري أول")


@pytest.fixture
def vice(school):
    return _member(school, "vice_admin", "نائب إداري اختباري")


def _post(client, pk, supervisor, *, action="save", day=None, recs=(), **extra):
    data = {
        "supervisor": str(supervisor.pk),
        "follow_date": (day or timezone.localdate()).isoformat(),
        "action": action,
        "strengths": STRENGTH,
        "improvements": "",
        "rating_1": "complete",
        "note_1": "ملاحظة",
        "rec_id": [r[0] for r in recs],
        "rec_text": [r[1] for r in recs],
        **extra,
    }
    return client.post(reverse("supervisor_followup_edit", args=[pk]), data)


def test_indicators_and_ratings_are_the_paper_text_in_order():
    assert [n for n, _ in INDICATORS] == list(range(1, 14))
    assert INDICATORS[0][1] == "حصر الغياب اليومي للطلاب وتوثيقه وإدخاله إلكترونيًا على نظام الغياب"
    assert "اتخاذ الإجراءات اللازمة" in INDICATORS[2][1]
    assert INDICATORS[12][1] == "المواظبة والانضباط في العمل"
    assert [label for _, label in RATINGS] == [
        "مستكمل",
        "مستكمل جزئياً",
        "غير مستكمل",
        "لم يتم قياسه",
    ]


def test_migration_matches_the_models():
    call_command("makemigrations", "quality", check=True, dry_run=True, verbosity=0)


def test_the_form_renders_in_paper_order_without_inline_code(client_as, vice, supervisor):
    response = client_as(vice).get(reverse("supervisor_followup_new", args=[supervisor.pk]))
    assert response.status_code == 200
    html = response.content.decode()
    order = [
        "متابعة التوصيات السابقة",
        "متابعة الغياب والاستئذان والتأخير الصباحي",
        "اسم المشرف الإداري",
        "مؤشرات المتابعة",
        "جوانب القوة",
        "جوانب تحتاج إلى تحسين",
        "إضافة توصية",
    ]
    positions = [html.index(text) for text in order]
    assert positions == sorted(positions)
    assert "data-draft-key=" in html and "حفظ مسودة" in html
    for _number, text in INDICATORS:
        assert text in html


def test_saving_twice_is_idempotent_and_draft_becomes_saved(client_as, vice, supervisor):
    client = client_as(vice)
    pk, rec = uuid.uuid4(), str(uuid.uuid4())
    for _ in range(2):
        assert (
            _post(client, pk, supervisor, action="draft", recs=[(rec, "توصية")]).status_code == 302
        )
    assert SupervisorFollowUp.objects.get().status == "draft"
    assert SupervisorFollowUpScore.objects.count() == 13
    assert SupervisorFollowUpRecommendation.objects.count() == 1
    # «متابعة جديدة» تفتح المسودةَ القائمة
    response = client.get(reverse("supervisor_followup_new", args=[supervisor.pk]))
    assert response.url == reverse("supervisor_followup_edit", args=[pk])
    for _ in range(2):
        assert _post(client, pk, supervisor, recs=[(rec, "توصية معدلة")]).status_code == 302
    assert SupervisorFollowUp.objects.get().status == "saved"
    assert SupervisorFollowUpRecommendation.objects.get().text == "توصية معدلة"
    # الحذفُ من النموذج حذفٌ ناعم
    _post(client, pk, supervisor)
    assert not SupervisorFollowUpRecommendation.objects.exists()
    assert SupervisorFollowUpRecommendation.all_objects.count() == 1


def test_previous_recommendations_are_reviewed_in_the_next_follow_up(client_as, vice, supervisor):
    client = client_as(vice)
    today = timezone.localdate()
    first, second, rec = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    _post(
        client, first, supervisor, day=today - dt.timedelta(days=7), recs=[(str(rec), "توصية أولى")]
    )
    html = client.get(reverse("supervisor_followup_new", args=[supervisor.pk])).content.decode()
    assert "توصية أولى" in html and f"review_status_{rec}" in html
    _post(
        client,
        second,
        supervisor,
        review_id=str(rec),
        **{f"review_status_{rec}": "done", f"review_note_{rec}": "تم"},
    )
    item = SupervisorFollowUpRecommendation.objects.get(pk=rec)
    assert (item.status, item.note, item.reviewed_in_id) == ("done", "تم", second)


def test_attendance_counts_are_computed_since_last_follow_up_and_snapshotted(
    client_as, school, vice, supervisor
):
    client = client_as(vice)
    today = timezone.localdate()
    last = today - dt.timedelta(days=20)
    _post(client, uuid.uuid4(), supervisor, day=last)

    def leave(kind, start, days, status="approved"):
        LeaveRequest.objects.create(
            school=school,
            staff=supervisor,
            leave_type=kind,
            start_date=start,
            end_date=start + dt.timedelta(days=days - 1),
            days_count=days,
            reason="اختبار",
            status=status,
        )

    leave("sick", last - dt.timedelta(days=1), 4)  # يومان منها داخل الفترة
    leave("emergency", today - dt.timedelta(days=3), 1)
    leave("unpaid", today - dt.timedelta(days=5), 2)
    leave("unpaid", today - dt.timedelta(days=9), 2, status="pending")
    PermitRequest.objects.create(
        school=school,
        staff=supervisor,
        permit_type="during_day",
        date=today - dt.timedelta(days=2),
        start_time=dt.time(9, 0),
        end_time=dt.time(10, 0),
        duration_minutes=60,
        reason="اختبار",
        status="approved",
    )
    for offset, minutes in ((1, 10), (2, 0), (30, 15)):
        StaffAttendance.objects.create(
            school=school,
            staff=supervisor,
            date=today - dt.timedelta(days=offset),
            status="late",
            late_minutes=minutes,
        )
    pk = uuid.uuid4()
    _post(client, pk, supervisor)
    saved = SupervisorFollowUp.objects.get(pk=pk)
    assert saved.period_start == last + dt.timedelta(days=1)
    assert saved.period_end == today
    assert (saved.sick_days, saved.casual_days, saved.unpaid_days) == (2, 1, 2)
    assert (saved.permit_count, saved.late_count) == (1, 1)
    # لقطة: حذفُ السجلّ المصدر لا يغيّر المحفوظ
    StaffAttendance.objects.all().delete()
    html = client.get(reverse("supervisor_followup_detail", args=[pk])).content.decode()
    assert "التأخير الصباحي: <b>1</b>" in html


def test_attendance_summary_uses_a_fixed_number_of_queries(
    school, supervisor, django_assert_max_num_queries
):
    from quality.supervisor_followup_selectors import attendance_summary

    with django_assert_max_num_queries(10):
        attendance_summary(school, supervisor, timezone.localdate(), None)


def test_future_date_is_refused_and_input_is_kept(client_as, vice, supervisor):
    response = _post(
        client_as(vice),
        uuid.uuid4(),
        supervisor,
        day=timezone.localdate() + dt.timedelta(days=1),
    )
    assert response.status_code == 200
    assert STRENGTH in response.content.decode()
    assert not SupervisorFollowUp.objects.exists()


def test_supervisor_reads_only_own_saved_follow_ups(client_as, school, principal_user, supervisor):
    other = _member(school, "admin_supervisor", "مشرف اختباري ثان")
    manager = client_as(principal_user)
    mine, draft, theirs = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    _post(manager, mine, supervisor, day=timezone.localdate() - dt.timedelta(days=1))
    _post(manager, draft, supervisor, action="draft")
    _post(manager, theirs, other)
    client = client_as(supervisor)
    listing = client.get(reverse("supervisor_followup_list"))
    assert listing.status_code == 200
    assert [f.pk for f in listing.context["history"]] == [mine]
    assert client.get(reverse("supervisor_followup_detail", args=[mine])).status_code == 200
    for pk in (draft, theirs):
        assert client.get(reverse("supervisor_followup_detail", args=[pk])).status_code == 403
    assert client.get(reverse("supervisor_followup_edit", args=[mine])).status_code == 403
    assert _post(client, mine, supervisor).status_code == 403
    assert client.get(reverse("supervisor_followup_new", args=[supervisor.pk])).status_code == 403
    assert client.post(reverse("supervisor_followup_delete", args=[mine])).status_code == 403


@pytest.mark.parametrize("role", ["vice_academic", "teacher", "coordinator", "student_observer"])
def test_other_roles_get_403(client_as, school, supervisor, role):
    client = client_as(_member(school, role, "مستخدم آخر"))
    assert client.get(reverse("supervisor_followup_list")).status_code == 403
    assert client.get(reverse("supervisor_followup_new", args=[supervisor.pk])).status_code == 403
    assert _post(client, uuid.uuid4(), supervisor).status_code == 403


def test_queries_are_scoped_to_the_school(client_as, vice, supervisor):
    elsewhere = SchoolFactory()
    stranger = _member(elsewhere, "admin_supervisor", "مشرف مدرسة أخرى")
    foreign = SupervisorFollowUp.objects.create(
        school=elsewhere,
        supervisor=stranger,
        follower=_member(elsewhere, "principal", "مدير أخرى"),
        status="saved",
    )
    client = client_as(vice)
    assert client.get(reverse("supervisor_followup_detail", args=[foreign.pk])).status_code == 404
    assert client.get(reverse("supervisor_followup_edit", args=[foreign.pk])).status_code == 404
    assert client.get(reverse("supervisor_followup_new", args=[stranger.pk])).status_code == 404
    _post(client, uuid.uuid4(), stranger)
    assert SupervisorFollowUp.objects.count() == 1
    listing = client.get(reverse("supervisor_followup_list"))
    assert listing.context["history"] == []
    assert [u.pk for u, _ in listing.context["supervisor_rows"]] == [supervisor.pk]


def test_audit_trail_has_no_names_or_free_text_and_delete_is_soft(client_as, vice, supervisor):
    client = client_as(vice)
    pk = uuid.uuid4()
    _post(client, pk, supervisor, action="draft")
    _post(client, pk, supervisor)
    assert client.post(reverse("supervisor_followup_delete", args=[pk])).status_code == 302
    assert not SupervisorFollowUp.objects.exists()
    assert SupervisorFollowUp.all_objects.get().is_deleted
    rows = AuditLog.objects.filter(object_id=str(pk))
    assert sorted(r.action for r in rows) == ["create", "delete", "update"]
    for row in rows:
        text = f"{row.object_repr} {row.changes}"
        assert supervisor.full_name not in text and STRENGTH not in text


def test_the_menu_link_is_offered_by_can_open(school, vice, principal_user, supervisor):
    from core.navigation import can_open

    for user in (vice, principal_user, supervisor):
        assert can_open(user, "supervisor_followup_list")
    other = _member(school, "vice_academic", "نائب أكاديمي")
    assert not can_open(other, "supervisor_followup_list")


def _act(client, name, pk, **data):
    return client.post(reverse(f"supervisor_followup_{name}", args=[pk]), data)


def _notes(user):
    return InAppNotification.objects.filter(user=user)


def test_send_is_for_saved_only_and_idempotent(client_as, vice, supervisor):
    client = client_as(vice)
    draft, saved = uuid.uuid4(), uuid.uuid4()
    _post(client, saved, supervisor)
    _post(client, draft, supervisor, action="draft")
    assert _act(client, "send", draft).status_code == 302
    assert SupervisorFollowUp.objects.get(pk=draft).status == "draft"
    assert not _notes(supervisor).exists()
    viewer = reverse("supervisor_followup_pdf_view", args=[saved])
    assert "إرسال للمشرف" in client.get(viewer).content.decode()
    _act(client, "send", saved)
    first = SupervisorFollowUp.objects.get(pk=saved)
    assert first.status == "sent" and first.sent_at
    _act(client, "send", saved)
    assert SupervisorFollowUp.objects.get(pk=saved).sent_at == first.sent_at
    note = _notes(supervisor).get()
    assert note.related_url == reverse("supervisor_followup_detail", args=[saved])
    assert not note.body and supervisor.full_name not in note.title
    assert "إرسال للمشرف" not in client.get(viewer).content.decode()
    # التعديلُ قبل الإقرار باقٍ ولا يُرجع الحالة
    assert _post(client, saved, supervisor).status_code == 302
    assert SupervisorFollowUp.objects.get(pk=saved).status == "sent"


def test_only_the_owner_acknowledges_a_sent_follow_up_once(client_as, school, vice, supervisor):
    pk = uuid.uuid4()
    _post(client_as(vice), pk, supervisor)
    # قبل الإرسال مرفوض
    assert _act(client_as(supervisor), "acknowledge", pk).status_code == 302
    assert SupervisorFollowUp.objects.get().status == "saved"
    assert _act(client_as(supervisor), "send", pk).status_code == 403
    _act(client_as(vice), "send", pk)
    detail = reverse("supervisor_followup_detail", args=[pk])
    assert "أقرّ بالاطّلاع" in client_as(supervisor).get(detail).content.decode()
    other = _member(school, "admin_supervisor", "مشرف اختباري ثان")
    teacher = _member(school, "teacher", "معلم اختباري")
    for stranger in (vice, other, teacher):
        assert _act(client_as(stranger), "acknowledge", pk).status_code == 403
    own = client_as(supervisor)
    _act(own, "acknowledge", pk, supervisor_comment=" تعليق حرّ ")
    first = SupervisorFollowUp.objects.get()
    assert (first.status, first.supervisor_comment) == ("acknowledged", "تعليق حرّ")
    assert first.acknowledged_at
    _act(own, "acknowledge", pk, supervisor_comment="تعليق ثان")
    again = SupervisorFollowUp.objects.get()
    assert again.supervisor_comment == "تعليق حرّ"
    assert again.acknowledged_at == first.acknowledged_at
    assert _notes(vice).count() == 1 and not _notes(vice).get().body
    assert [f.pk for f in own.get(reverse("supervisor_followup_list")).context["history"]] == [pk]
    for url in (detail, reverse("supervisor_followup_list")):
        html = client_as(vice).get(url).content.decode()
        assert "أُقرّت" in html and "تعليق حرّ" in html
    rows = AuditLog.objects.filter(object_id=str(pk))
    assert sorted(r.changes["status"] for r in rows) == ["acknowledged", "saved", "sent"]
    for row in rows:
        text = f"{row.object_repr} {row.changes}"
        assert supervisor.full_name not in text and "تعليق حرّ" not in text


def test_acknowledged_follow_up_is_locked(client_as, vice, supervisor):
    pk = uuid.uuid4()
    _post(client_as(vice), pk, supervisor)
    _act(client_as(vice), "send", pk)
    _act(client_as(supervisor), "acknowledge", pk)
    manager = client_as(vice)
    edit = reverse("supervisor_followup_edit", args=[pk])
    responses = [
        manager.get(edit),
        _post(manager, pk, supervisor, strengths="تغيير"),
        _post(manager, pk, supervisor, day=timezone.localdate() + dt.timedelta(days=1)),
        _act(manager, "delete", pk),
    ]
    for response in responses:
        assert response.status_code == 403
        assert "المتابعة مقفلة" in response.content.decode()
    saved = SupervisorFollowUp.objects.get()
    assert saved.strengths == STRENGTH and not saved.is_deleted
    assert edit not in manager.get(reverse("supervisor_followup_list")).content.decode()


def test_another_school_cannot_send_or_acknowledge(client_as, vice, supervisor):
    pk = uuid.uuid4()
    _post(client_as(vice), pk, supervisor)
    elsewhere = SchoolFactory()
    for role in ("principal", "admin_supervisor"):
        client = client_as(_member(elsewhere, role, "مستخدم مدرسة أخرى"))
        for name in ("send", "acknowledge"):
            assert _act(client, name, pk).status_code in (403, 404)
        assert client.get(reverse("supervisor_followup_pdf", args=[pk])).status_code in (403, 404)
    assert SupervisorFollowUp.objects.get().status == "saved"


def test_assets_follow_csp_rtl_and_token_rules():
    for name in ("list", "form", "detail", "pdf_view", "locked"):
        html = pathlib.Path(f"templates/quality/supervisor_followup_{name}.html").read_text(
            encoding="utf-8"
        )
        assert "style=" not in html and "onclick" not in html and "<script nonce" not in html
    css = pathlib.Path("static/css/custom/33-modules-4.css").read_text(encoding="utf-8")
    block = css[css.index("متابعة المشرف الإداري (نموذج 19)") :]
    for banned in ("px", "#", "left", "right"):
        assert banned not in block.split("@layer modules {", 1)[1]

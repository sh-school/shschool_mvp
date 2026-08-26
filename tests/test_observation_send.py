"""
tests/test_observation_send.py
إرسال نسخةٍ من الزيارة الصفّية إلى الجهات الأكاديميّة + الصفحة العارضة للـPDF.

الـPDF يُعاد بـ`Content-Disposition: inline`، فيحلّ عارضُ المتصفّح محلّ الصفحة
كاملةً: لا رجوع ولا إجراء. وحقنُ زرٍّ داخل الملفّ غير ممكن، فوُضع الملفّ داخل
صفحةٍ عارضة يبقى شريط أدواتها لنا.
"""

import pytest
from django.urls import reverse

from core.models import Department, Membership, Role
from quality.observation_models import ClassroomObservation, ObservationCriterion
from quality.observation_services import ObservationService


def _make_obs(school, observer, teacher):
    obs = ClassroomObservation.objects.create(
        school=school, teacher=teacher, observer=observer, created_by=observer
    )
    crit, _ = ObservationCriterion.objects.get_or_create(
        school=school, domain="planning", text="معيار", defaults={"order": 1}
    )
    ObservationService.save_scores(obs, {str(crit.id): "complete"}, {})
    obs.refresh_from_db()
    return obs


def _put_in_department(school, teacher, head):
    """يضع المعلّم في قسمٍ رئيسُه `head` — وهو الرابط الوحيد معلّم↔منسّق."""
    dept = Department.objects.create(school=school, name="الرياضيات", code="MATH", head=head)
    Membership.objects.filter(user=teacher, school=school).update(department_obj=dept)
    return dept


def _vice_academic(school, name="النائب الأكاديميّ"):
    from tests.conftest import MembershipFactory, UserFactory

    role, _ = Role.objects.get_or_create(school=school, name="vice_academic")
    user = UserFactory(full_name=name)
    MembershipFactory(user=user, school=school, role=role)
    return user


# ══════════════════════ استخراج المستلمين ════════════════════════════


@pytest.mark.django_db
def test_the_coordinator_is_resolved_through_the_department(
    school, principal_user, teacher_user, coordinator_user
):
    """لا ربط مباشر معلّم↔منسّق؛ الرابط هو القسم ورئيسُه."""
    _put_in_department(school, teacher_user, coordinator_user)
    obs = _make_obs(school, principal_user, teacher_user)

    found = {k: u for k, _l, u in ObservationService.recipient_options(obs)}

    assert found["coordinator"] == coordinator_user


@pytest.mark.django_db
def test_a_department_without_a_head_yields_no_coordinator(school, principal_user, teacher_user):
    """قسمٌ بلا رئيس يُعيد `None` لا يرفع استثناءً — الغياب حالةٌ متوقّعة."""
    Department.objects.create(school=school, name="العلوم", code="SCI")
    obs = _make_obs(school, principal_user, teacher_user)

    found = {k: u for k, _l, u in ObservationService.recipient_options(obs)}

    assert found["coordinator"] is None


@pytest.mark.django_db
def test_the_four_recipients_keep_a_stable_order(school, principal_user, teacher_user):
    obs = _make_obs(school, principal_user, teacher_user)

    keys = [k for k, _l, _u in ObservationService.recipient_options(obs)]

    assert keys == ["teacher", "coordinator", "vice_academic", "principal"]


# ══════════════════════ الإرسال ══════════════════════════════════════


@pytest.mark.django_db
def test_only_the_chosen_recipients_receive_a_copy(
    school, principal_user, teacher_user, coordinator_user
):
    _put_in_department(school, teacher_user, coordinator_user)
    obs = _make_obs(school, principal_user, teacher_user)

    sent = ObservationService.send_copy(obs, principal_user, ["teacher"])

    assert sent == [teacher_user.full_name]


@pytest.mark.django_db
def test_the_sender_is_never_sent_a_copy_of_their_own_send(school, principal_user, teacher_user):
    """المدير يُرسل ويختار «مدير المدرسة» — إشعارُ نفسه ضجيجٌ لا فائدة فيه."""
    obs = _make_obs(school, principal_user, teacher_user)

    sent = ObservationService.send_copy(obs, principal_user, ["principal", "teacher"])

    assert principal_user.full_name not in sent
    assert sent == [teacher_user.full_name]


@pytest.mark.django_db
def test_a_missing_role_holder_is_skipped_not_reported_as_sent(
    school, principal_user, teacher_user
):
    """«لم أُرسل» لا تُقرأ «أرسلت».

    الاسم لا يظهر في الحصيلة إن لم يوجد شاغلٌ للدور — وإلا أعطت الرسالة
    للمُرسِل يقيناً بأن نائباً أكاديميّاً غير موجود قد اطّلع.
    """
    obs = _make_obs(school, principal_user, teacher_user)

    sent = ObservationService.send_copy(obs, principal_user, ["vice_academic", "teacher"])

    assert sent == [teacher_user.full_name]


@pytest.mark.django_db
def test_one_person_holding_two_roles_is_notified_once(school, principal_user, teacher_user):
    """المنسّق قد يكون هو النائب الأكاديميّ نفسه — إشعارٌ واحد لا اثنان."""
    vice = _vice_academic(school)
    _put_in_department(school, teacher_user, vice)
    obs = _make_obs(school, principal_user, teacher_user)

    sent = ObservationService.send_copy(obs, principal_user, ["coordinator", "vice_academic"])

    assert sent == [vice.full_name]


@pytest.mark.django_db
def test_sending_does_not_touch_the_workflow_state(school, principal_user, teacher_user):
    """التوزيع الإداريّ للاطّلاع ليس `submit`.

    خلطُهما يجعل زرّ مشاركةٍ يُغيّر حالةً رسميّة ويستهلك `submission_count`
    بلا أن يقصد المستخدم ذلك.
    """
    obs = _make_obs(school, principal_user, teacher_user)
    before = (obs.status, obs.submitted_at, obs.submission_count)

    ObservationService.send_copy(obs, principal_user, ["teacher"])
    obs.refresh_from_db()

    assert (obs.status, obs.submitted_at, obs.submission_count) == before


# ══════════════════════ الصفحة العارضة والصلاحية ══════════════════════


@pytest.mark.django_db
def test_the_viewer_page_offers_a_way_back(client, school, principal_user, teacher_user):
    """الرجوع هو سبب وجود هذه الصفحة أصلاً."""
    obs = _make_obs(school, principal_user, teacher_user)
    client.force_login(principal_user)

    html = client.get(reverse("observation_pdf_view", args=[obs.id])).content.decode()

    assert reverse("observation_detail", args=[obs.id]) in html
    assert reverse("observation_pdf", args=[obs.id]) in html


@pytest.mark.django_db
def test_a_teacher_may_send_a_copy_of_their_own_observation(
    client, school, principal_user, teacher_user
):
    obs = _make_obs(school, principal_user, teacher_user)
    client.force_login(teacher_user)

    resp = client.post(reverse("observation_send", args=[obs.id]), {"recipients": ["principal"]})

    assert resp.status_code == 302


@pytest.mark.django_db
def test_sending_with_no_recipient_chosen_changes_nothing(
    client, school, principal_user, teacher_user
):
    obs = _make_obs(school, principal_user, teacher_user)
    client.force_login(principal_user)

    resp = client.post(reverse("observation_send", args=[obs.id]), {})

    assert resp.status_code == 302
    obs.refresh_from_db()
    assert obs.status == "draft"


@pytest.mark.django_db
def test_a_stranger_cannot_reach_the_viewer(client, school, principal_user, teacher_user):
    """الرؤية تسبق الصلاحية: معلّمٌ آخر لا يرى زيارةً ليست له."""
    from tests.conftest import MembershipFactory, UserFactory

    obs = _make_obs(school, principal_user, teacher_user)
    role, _ = Role.objects.get_or_create(school=school, name="teacher")
    other = UserFactory(full_name="معلّم آخر")
    MembershipFactory(user=other, school=school, role=role)
    client.force_login(other)

    resp = client.get(reverse("observation_pdf_view", args=[obs.id]))

    assert resp.status_code == 403


# ══════════════════════ ترويسة الوثيقة ══════════════════════════════


@pytest.mark.django_db
def test_the_pdf_carries_the_school_letterhead(client, school, principal_user, teacher_user):
    """الترويسة تُقرأ من `obs.school` لا تُكتب نصّاً في القالب.

    قوالب الطباعة الأخرى تُثبّت اسم المدرسة وهاتفها صراحةً — وذلك يطبع ترويسة
    مدرسةٍ على وثيقة أخرى في منصّةٍ متعدّدة المدارس.
    """
    obs = _make_obs(school, principal_user, teacher_user)
    client.force_login(principal_user)

    resp = client.get(reverse("observation_pdf", args=[obs.id]))

    assert resp.status_code == 200
    assert resp["Content-Type"] == "application/pdf"
    assert resp.content[:4] == b"%PDF"


@pytest.mark.django_db
def test_the_letterhead_markup_reads_the_school_not_a_hardcoded_name(
    school, principal_user, teacher_user
):
    from django.template.loader import render_to_string

    from quality.observation_views import _groups_with_scores

    obs = _make_obs(school, principal_user, teacher_user)
    html = render_to_string(
        "quality/observation_pdf.html",
        {"obs": obs, "grouped": _groups_with_scores(obs), "rating_choices": []},
    )

    assert "doc-header" in html
    assert "وزارة التربية والتعليم والتعليم العالي" in html
    assert school.name in html


# ══════════════════════ الصفحة تُعرض فعلاً ══════════════════════════


@pytest.mark.django_db
def test_the_pdf_may_be_framed_by_its_own_viewer(client, school, principal_user, teacher_user):
    """`X_FRAME_OPTIONS = "DENY"` عامٌّ، فكان يمنع الملفّ من الظهور داخل صفحته.

    والمتصفّح لا يُبلّغ عن ذلك في السجلّ — يضع «refused to connect» مكان الملفّ،
    فتبدو الصفحة سليمةً وهي فارغة. والاستثناء `sameorigin` لهذه الاستجابة وحدها،
    وكلّ ما عداها يبقى على `DENY`.
    """
    obs = _make_obs(school, principal_user, teacher_user)
    client.force_login(principal_user)

    resp = client.get(reverse("observation_pdf", args=[obs.id]))

    assert resp.headers.get("X-Frame-Options") == "SAMEORIGIN"


@pytest.mark.django_db
def test_the_viewer_page_renders_no_stray_template_syntax(
    client, school, principal_user, teacher_user
):
    """`{# … #}` في Django سطرٌ واحد — والمتعدّد يُطبع نصّاً فوق الصفحة.

    وقع ذلك فعلاً وظهر التعليق للمستخدمين. والصيغة الصحيحة `{% comment %}`.
    """
    obs = _make_obs(school, principal_user, teacher_user)
    client.force_login(principal_user)

    html = client.get(reverse("observation_pdf_view", args=[obs.id])).content.decode()

    assert "{#" not in html
    assert "{%" not in html

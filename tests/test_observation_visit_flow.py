"""[QUALITY] تدفّقُ الزيارة الصفّيّة بين الزائر والمُزار — الإرسالُ الصريحُ والظهورُ والتوقيعان (W-20260929-004).

بلاغ المالك: الزيارةُ تُرسَل للمعلّم بلا زرّ إرسالٍ صريح، وتوقيعُ الزائر يعرض توقيعَ المُزار خطأً، والزيارةُ لا تظهر
عند المُزار بعد الإرسال. والمرجعُ منطقُ ظهور التوقيعات: `docs/quality/observation_signatures.md`.

الاختباراتُ بالاتجاهين: الزائر←المُزار (يرسل فيرى المُزارُ ويُشعَر) والمُزار←الزائر (يطّلع فيرى الزائرُ ويُشعَر)،
ولزيارتَي الإشراف والزميل معاً. والإشعارُ يُلتقط من `NotificationHub.dispatch` لا من جدولٍ يتبدّل شكلُه.
"""

import re

import pytest
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from core.models import CustomUser
from core.models.access import Membership, Role
from quality.observation_models import ClassroomObservation, ObservationCriterion
from quality.observation_services import ObservationService
from quality.observation_views import _pdf_context
from quality.presentation import signature_stamps

pytestmark = pytest.mark.pin_clock

HOST = "localhost"


@pytest.fixture
def person(db, school):
    def _make(name, role_name="teacher"):
        user = CustomUser.objects.create(
            must_change_password=False,
            national_id=f"286{abs(hash(name)) % 10**8:08d}",
            full_name=name,
        )
        role, _ = Role.objects.get_or_create(school=school, name=role_name)
        Membership.objects.create(user=user, school=school, role=role)
        return user

    return _make


@pytest.fixture
def criterion(db, school):
    return ObservationCriterion.objects.create(
        school=school, domain="planning", text="معيارٌ", order=1
    )


@pytest.fixture
def notices(monkeypatch):
    """ما أُرسل من إشعارات: [(المستلم، العنوان)] — بلا لمس جدول الإشعارات."""
    sent: list[tuple[CustomUser, str]] = []

    def _dispatch(*, recipients, title, **_kw):
        sent.extend((r, title) for r in recipients)

    monkeypatch.setattr("notifications.hub.NotificationHub.dispatch", _dispatch)
    return sent


def _client(user):
    c = Client()
    c.force_login(user)
    return c


def _make(school, observer, teacher, kind, criterion, status="draft"):
    obs = ClassroomObservation.objects.create(
        school=school,
        teacher=teacher,
        observer=observer,
        created_by=observer,
        kind=kind,
        topic="موضوعٌ مميَّز",
    )
    ObservationService.save_scores(obs, {str(criterion.id): "complete"}, {})
    if status != "draft":
        ObservationService.submit(obs, observer)
    if status == "acknowledged":
        ObservationService.acknowledge(obs, "")
    obs.refresh_from_db()
    return obs


#: (النوع، دورُ الزائر) — زيارةُ إشرافٍ من النائب الأكاديميّ، وزيارةُ زميلٍ من معلّم.
KINDS = [("supervision", "vice_academic"), ("peer", "teacher")]


# ══════════════ زرُّ الإرسال الصريح: Enter لا يرسل ═══════════════════════


@pytest.mark.parametrize(
    "url_name", ["observation_create", "observation_peer_create", "observation_self_create"]
)
def test_the_first_submit_button_is_the_draft_one(db, person, url_name):
    """الإدخالُ الضمنيّ (Enter في حقلٍ نصّيّ) يضغط أوّلَ زرّ إرسالٍ في الاستمارة — فلو كان «إرسال للمعلّم» الأوّلَ
    أُرسلت الزيارةُ بلا قصد. فأوّلُ زرٍّ حفظُ المسوّدة (لا أثرَ له على المُزار)، والإرسالُ بالنقر الصريح وحدَه."""
    role = "vice_academic" if url_name == "observation_create" else "teacher"
    body = _client(person("زائر", role)).get(reverse(url_name), HTTP_HOST=HOST).content.decode()

    start = body.index('<form method="post" class="qobs-form-stack"')
    form = body[start : body.index("</form>", start)]
    first = re.search(r'<button[^>]*type="submit"[^>]*>', form)
    assert first and 'value="draft"' in first.group(0)
    assert 'value="submit"' in form  # الزرُّ الصريحُ موجودٌ أيضاً


# ══════════════ الظهور عند المُزار ═══════════════════════════════════════


@pytest.mark.parametrize(("kind", "role"), KINDS)
def test_a_draft_is_hidden_from_the_visited_person(db, school, person, criterion, kind, role):
    visitor, visited = person("فلان الزائر", role), person("فلان المُزار")
    obs = _make(school, visitor, visited, kind, criterion)

    listing = _client(visited).get(reverse("observation_list"), HTTP_HOST=HOST).content.decode()
    detail = _client(visited).get(reverse("observation_detail", args=[obs.id]), HTTP_HOST=HOST)

    assert "فلان الزائر" not in listing
    assert detail.status_code == 404  # لا 403: وجودُ المسوّدة لا يُكشف للمُزار


@pytest.mark.parametrize(("kind", "role"), KINDS)
def test_a_sent_visit_appears_for_the_visited_person(
    db, school, person, criterion, notices, kind, role
):
    visitor, visited = person("فلان الزائر", role), person("فلان المُزار")
    obs = _make(school, visitor, visited, kind, criterion)

    resp = _client(visitor).post(reverse("observation_submit", args=[obs.id]), HTTP_HOST=HOST)

    assert resp.status_code == 302
    listing = _client(visited).get(reverse("observation_list"), HTTP_HOST=HOST).content.decode()
    detail = _client(visited).get(reverse("observation_detail", args=[obs.id]), HTTP_HOST=HOST)
    assert "فلان الزائر" in listing
    assert detail.status_code == 200
    assert [r for r, _t in notices] == [visited]


@pytest.mark.parametrize(("kind", "role"), KINDS)
def test_saving_a_draft_from_the_form_does_not_send(
    db, school, person, criterion, notices, kind, role
):
    visitor, visited = person("فلان الزائر", role), person("فلان المُزار")
    url = reverse("observation_create" if kind == "supervision" else "observation_peer_create")

    _client(visitor).post(
        url, {"teacher": str(visited.id), "topic": "مسوّدة", "action": "draft"}, HTTP_HOST=HOST
    )

    obs = ClassroomObservation.objects.get(kind=kind)
    assert obs.status == "draft" and obs.submitted_at is None
    assert not notices


@pytest.mark.parametrize(("kind", "role"), KINDS)
def test_the_form_send_button_sends_and_notifies(
    db, school, person, criterion, notices, kind, role
):
    visitor, visited = person("فلان الزائر", role), person("فلان المُزار")
    url = reverse("observation_create" if kind == "supervision" else "observation_peer_create")

    _client(visitor).post(
        url, {"teacher": str(visited.id), "topic": "مرسَلة", "action": "submit"}, HTTP_HOST=HOST
    )

    obs = ClassroomObservation.objects.get(kind=kind)
    assert obs.status == "submitted"
    assert [r for r, _t in notices] == [visited]


# ══════════════ الاتجاه العكسيّ: المُزار يطّلع فيرى الزائر ═════════════════


@pytest.mark.parametrize(("kind", "role"), KINDS)
def test_the_visited_person_acknowledges_and_the_visitor_sees_it(
    db, school, person, criterion, notices, kind, role
):
    visitor, visited = person("فلان الزائر", role), person("فلان المُزار")
    obs = _make(school, visitor, visited, kind, criterion, status="submitted")
    notices.clear()

    _client(visited).post(
        reverse("observation_acknowledge", args=[obs.id]),
        {"teacher_comment": "شكراً"},
        HTTP_HOST=HOST,
    )

    obs.refresh_from_db()
    assert obs.status == "acknowledged"
    assert [r for r, _t in notices] == [visitor]
    detail = _client(visitor).get(reverse("observation_detail", args=[obs.id]), HTTP_HOST=HOST)
    assert detail.status_code == 200 and "شكراً" in detail.content.decode()


def test_only_the_visited_person_may_acknowledge(db, school, person, criterion):
    visitor, visited, other = person("الزائر", "vice_academic"), person("المُزار"), person("غيره")
    obs = _make(school, visitor, visited, "supervision", criterion, status="submitted")

    for who in (visitor, other):
        _client(who).post(reverse("observation_acknowledge", args=[obs.id]), HTTP_HOST=HOST)

    obs.refresh_from_db()
    assert obs.status == "submitted"


# ══════════════ توقيعا الزائر والمُزار ═══════════════════════════════════


def _cell(html, label):
    """نصُّ خانة التوقيع التي بعد عنوانها `label` في الاستمارة المطبوعة."""
    m = re.search(
        rf'<td class="band sign"[^>]*>{label}</td>\s*<td class="sign"[^>]*>(.*?)</td>', html, re.S
    )
    assert m, label
    return re.sub(r"<[^>]+>", " ", m.group(1)).split()


def _printed(obs):
    from django.template.loader import render_to_string

    return render_to_string("quality/observation_pdf.html", _pdf_context(obs))


#: الحالةُ ← (توقيعُ الزائر، توقيعُ المُزار): الزائرُ بعد الإرسال، والمُزارُ بعد اطّلاعه، وما قبلهما خانةٌ فارغة.
SIGNATURES = {
    "draft": (False, False),
    "submitted": (True, False),
    "acknowledged": (True, True),
}


@pytest.mark.parametrize("status", list(SIGNATURES))
@pytest.mark.parametrize(("kind", "role"), KINDS)
def test_each_signature_sits_in_its_own_cell(db, school, person, criterion, status, kind, role):
    visitor, visited = person("اسمُ الزائر", role), person("اسمُ المُزار")
    obs = _make(school, visitor, visited, kind, criterion, status=status)
    html = _printed(obs)

    visitor_cell, visited_cell = _cell(html, "توقيع الزائر"), _cell(html, "توقيع المعلم")

    sees_visitor, sees_visited = SIGNATURES[status]
    assert ("اسمُ الزائر" in " ".join(visitor_cell)) is sees_visitor
    assert ("اسمُ المُزار" in " ".join(visited_cell)) is sees_visited
    # لا يتسرّب اسمُ أحدهما إلى خانة الآخر أبداً
    assert "اسمُ المُزار" not in " ".join(visitor_cell)
    assert "اسمُ الزائر" not in " ".join(visited_cell)


def test_withdrawing_removes_the_visitor_signature(db, school, person, criterion):
    visitor, visited = person("الزائر", "vice_academic"), person("المُزار")
    obs = _make(school, visitor, visited, "supervision", criterion, status="submitted")

    ObservationService.withdraw(obs, visitor)
    obs.refresh_from_db()

    assert signature_stamps(obs) == {"visitor": None, "teacher": None}


def test_reopening_removes_the_teacher_signature_only(db, school, person, criterion):
    visitor, visited = person("الزائر", "vice_academic"), person("المُزار")
    obs = _make(school, visitor, visited, "supervision", criterion, status="acknowledged")

    ObservationService.reopen(obs, visitor)
    obs.refresh_from_db()

    stamps = signature_stamps(obs)
    assert stamps["visitor"] == {"name": "الزائر"} and stamps["teacher"] is None


def test_a_stale_time_on_a_draft_stamps_nothing(db, school, person, criterion):
    """الحالةُ هي الحكمُ لا الوقتُ وحدَه: وقتٌ عالقٌ على مسوّدةٍ لا يُختم."""
    visitor, visited = person("الزائر", "vice_academic"), person("المُزار")
    obs = _make(school, visitor, visited, "supervision", criterion)
    obs.submitted_at = obs.teacher_acknowledged_at = timezone.now()

    assert signature_stamps(obs) == {"visitor": None, "teacher": None}


def test_leadership_and_the_visitor_still_see_the_draft(db, school, person, criterion):
    visitor, visited = person("فلان الزائر", "vice_academic"), person("فلان المُزار")
    lead = person("فلان القائد", "principal")
    obs = _make(school, visitor, visited, "supervision", criterion)

    for who in (visitor, lead):
        assert (
            _client(who)
            .get(reverse("observation_detail", args=[obs.id]), HTTP_HOST=HOST)
            .status_code
            == 200
        )
        assert (
            "فلان الزائر"
            in _client(who).get(reverse("observation_list"), HTTP_HOST=HOST).content.decode()
        )


def test_withdrawing_hides_the_visit_and_its_notice_does_not_link_to_it(
    db, school, person, criterion, monkeypatch
):
    visitor, visited = person("فلان الزائر", "vice_academic"), person("فلان المُزار")
    obs = _make(school, visitor, visited, "supervision", criterion, status="submitted")
    links = []
    monkeypatch.setattr(
        "notifications.hub.NotificationHub.dispatch", lambda **kw: links.append(kw["related_url"])
    )

    ObservationService.withdraw(obs, visitor)

    assert links == ["/quality/observations/"]
    assert str(obs.id) not in links[0]
    assert (
        _client(visited)
        .get(reverse("observation_detail", args=[obs.id]), HTTP_HOST=HOST)
        .status_code
        == 404
    )


def test_the_peer_notice_carries_no_scores(db, school, person, criterion, monkeypatch):
    visitor, visited = person("فلان الزائر"), person("فلان المُزار")
    obs = _make(school, visitor, visited, "peer", criterion)
    bodies = []
    monkeypatch.setattr(
        "notifications.hub.NotificationHub.dispatch", lambda **kw: bodies.append(kw["body"])
    )

    ObservationService.submit(obs, visitor)

    assert len(bodies) == 1 and "فلان الزائر" in bodies[0] and "موضوعٌ مميَّز" in bodies[0]
    assert "%" not in bodies[0] and "النسبة" not in bodies[0]


def test_a_self_assessment_notifies_no_one(db, school, person, criterion, notices):
    me = person("فلان المعلّم")
    obs = _make(school, me, me, "self", criterion)

    ObservationService.submit(obs, me)

    assert not notices


def test_self_assessment_signs_only_in_the_teacher_cell(db, school, person, criterion):
    """التقييمُ الذاتيّ (W-027): يوقّعه المعلّمُ وحده، وخانةُ «اطّلاع المسؤول المباشر» فارغةٌ تُملأ بخطّ اليد (لا إقرارَ في self)."""
    me = person("فلان المعلّم")
    obs = _make(school, me, me, "self", criterion, status="submitted")
    html = _printed(obs)

    assert "فلان المعلّم" in " ".join(_cell(html, "توقيع المعلم"))
    assert "توقيع الزائر" not in html
    assert _cell(html, "اطّلاع المسؤول المباشر") == []
    ack = _client(me).post(reverse("observation_acknowledge", args=[obs.id]), HTTP_HOST=HOST)
    assert ack.status_code == 403
    obs.refresh_from_db()
    assert obs.status == "submitted"

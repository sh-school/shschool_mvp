"""[BEHAVIOR] قرارُ لجنة الضبط جماعيٌّ بأغلبيّة الأعضاء المؤهَّلين (D-116م، W-20261001-024).

كان أيُّ عضوٍ واحدٍ يُنفّذ التصعيدَ أو الإيقافَ فوراً. الآن `escalate` و`suspend` يحتاجان أغلبيّةَ
المدير والنائبين والأخصائيّ الاجتماعيّ وspecialist؛ و`resolve` بعضوٍ واحد؛ ولا تفويضَ عن غائب.
"""

import pytest

from behavior.committee_quorum import cast_vote, eligible_member_ids, majority_needed
from behavior.models import BehaviorCommitteeVote
from tests.conftest import (
    BehaviorInfractionFactory,
    MembershipFactory,
    RoleFactory,
    UserFactory,
)

pytestmark = pytest.mark.django_db


@pytest.fixture
def infraction(school, student_user, teacher_user):
    return BehaviorInfractionFactory(
        school=school, student=student_user, reported_by=teacher_user, level=3, is_resolved=False
    )


@pytest.fixture
def committee(school, principal_user):
    """لجنةٌ من خمسة: المدير + نائبان + أخصائيّان — الأغلبيّةُ ثلاثة."""
    members = [principal_user]
    for name in ("vice_admin", "vice_academic", "social_worker", "specialist"):
        user = UserFactory(full_name=name)
        MembershipFactory(user=user, school=school, role=RoleFactory(school=school, name=name))
        members.append(user)
    return members


def _url(infraction):
    return f"/behavior/committee/{infraction.id}/decision/"


def test_majority_is_more_than_half():
    assert [majority_needed(n) for n in (1, 2, 3, 4, 5)] == [1, 2, 2, 3, 3]


def test_eligible_members_are_the_committee_roles_of_the_school(school, committee, teacher_user):
    assert eligible_member_ids(school) == {u.pk for u in committee}
    assert teacher_user.pk not in eligible_member_ids(school)


def test_one_member_cannot_escalate(client_as, committee, infraction):
    resp = client_as(committee[0]).post(_url(infraction), {"decision": "escalate"})

    assert resp.status_code == 302
    infraction.refresh_from_db()
    assert infraction.level == 3, "عضوٌ واحدٌ من خمسة لا يصعّد"
    assert BehaviorCommitteeVote.objects.filter(infraction=infraction, status="open").count() == 1


def test_one_member_cannot_suspend(client_as, committee, infraction):
    client_as(committee[0]).post(
        _url(infraction), {"decision": "suspend", "action_taken": "إيقاف", "suspension_days": 2}
    )

    infraction.refresh_from_db()
    assert "إيقاف مؤقت" not in infraction.action_taken
    assert not infraction.suspension_days or infraction.suspension_days == 1


def test_majority_escalates_once_it_completes(client_as, committee, infraction):
    for member in committee[:2]:
        client_as(member).post(_url(infraction), {"decision": "escalate"})
    infraction.refresh_from_db()
    assert infraction.level == 3, "اثنان من خمسة لا يكفيان"

    client_as(committee[2]).post(_url(infraction), {"decision": "escalate"})

    infraction.refresh_from_db()
    assert infraction.level == 4
    votes = BehaviorCommitteeVote.objects.filter(infraction=infraction)
    assert votes.count() == 3 and all(
        v.status == "applied" for v in votes
    ), "الأصواتُ تبقى سجلَّ تدقيق"


def test_majority_suspends_with_the_closing_members_terms(client_as, committee, infraction):
    for member in committee[:3]:
        client_as(member).post(
            _url(infraction),
            {"decision": "suspend", "action_taken": "إيقاف", "suspension_days": 3},
        )

    infraction.refresh_from_db()
    assert "إيقاف مؤقت" in infraction.action_taken
    assert infraction.suspension_days == 3


def test_votes_for_different_decisions_do_not_add_up(client_as, committee, infraction):
    client_as(committee[0]).post(_url(infraction), {"decision": "escalate"})
    client_as(committee[1]).post(_url(infraction), {"decision": "suspend"})
    client_as(committee[2]).post(_url(infraction), {"decision": "escalate"})

    infraction.refresh_from_db()
    assert infraction.level == 3, "صوتان للتصعيد وصوتٌ للإيقاف — لا أغلبيّةَ لأيٍّ منهما"


def test_a_member_voting_twice_counts_once(client_as, committee, infraction):
    for _ in range(3):
        client_as(committee[0]).post(_url(infraction), {"decision": "escalate"})

    infraction.refresh_from_db()
    assert infraction.level == 3
    assert BehaviorCommitteeVote.objects.filter(infraction=infraction).count() == 1


def test_absent_members_are_not_substituted(client_as, committee, infraction):
    """لا تفويض: الأغلبيّةُ من الأعضاء المؤهَّلين، وصوتُ غيرهم لا يُحتسب."""
    outsider = UserFactory(full_name="غير عضو")
    MembershipFactory(
        user=outsider,
        school=infraction.school,
        role=RoleFactory(school=infraction.school, name="teacher"),
    )
    client_as(committee[0]).post(_url(infraction), {"decision": "escalate"})
    client_as(committee[1]).post(_url(infraction), {"decision": "escalate"})

    client_as(outsider).post(_url(infraction), {"decision": "escalate"})

    infraction.refresh_from_db()
    assert infraction.level == 3


def test_a_superuser_who_is_not_a_member_cannot_complete_the_quorum(
    committee, infraction, django_user_model
):
    admin = django_user_model.objects.create(
        national_id="28700000077", full_name="سوبريوزر", is_superuser=True
    )
    for member in committee[:2]:
        cast_vote(infraction, member, "escalate")

    message, level = cast_vote(infraction, admin, "escalate")

    infraction.refresh_from_db()
    assert infraction.level == 3 and level == "error", message


def test_resolve_stays_with_a_single_member(client_as, committee, infraction):
    client_as(committee[3]).post(_url(infraction), {"decision": "resolve"})

    infraction.refresh_from_db()
    assert infraction.is_resolved is True


def test_a_one_member_committee_decides_alone(client_as, principal_user, infraction):
    """مدرسةٌ ليس فيها إلا المدير: أغلبيّةُ واحدٍ هي واحد — لا جمود."""
    client_as(principal_user).post(_url(infraction), {"decision": "escalate"})

    infraction.refresh_from_db()
    assert infraction.level == 4


def test_applied_and_dropped_votes_stay_as_an_audit_trail(client_as, committee, infraction):
    client_as(committee[0]).post(_url(infraction), {"decision": "suspend"})
    for member in committee[1:4]:
        client_as(member).post(_url(infraction), {"decision": "escalate"})

    infraction.refresh_from_db()
    assert infraction.level == 4
    by_status = {
        status: BehaviorCommitteeVote.objects.filter(infraction=infraction, status=status).count()
        for status in ("open", "applied", "dropped")
    }
    assert by_status == {"open": 0, "applied": 3, "dropped": 1}


def test_changing_a_vote_to_complete_the_quorum_uses_the_voters_own_terms(
    client_as, committee, infraction
):
    """مراجعة 0105: التعديلُ لا يُنفّذ بمعاملات صوتٍ آخرَ أُنشئ لاحقاً."""
    client_as(committee[0]).post(_url(infraction), {"decision": "escalate"})
    client_as(committee[1]).post(
        _url(infraction), {"decision": "suspend", "action_taken": "إيقافُ الثاني"}
    )
    client_as(committee[2]).post(
        _url(infraction), {"decision": "suspend", "action_taken": "إيقافُ الثالث"}
    )
    client_as(committee[0]).post(
        _url(infraction), {"decision": "suspend", "action_taken": "إيقافُ الأوّل بعد تغيير صوته"}
    )

    infraction.refresh_from_db()
    assert "إيقافُ الأوّل بعد تغيير صوته" in infraction.action_taken
    assert "إيقافُ الثالث" not in infraction.action_taken


def test_mixed_suspension_terms_take_the_lighter_of_what_the_majority_agreed(
    client_as, committee, infraction
):
    terms = [(5, "external"), (2, "internal"), (3, "external")]
    for member, (days, kind) in zip(committee, terms, strict=False):
        client_as(member).post(
            _url(infraction),
            {"decision": "suspend", "suspension_days": days, "suspension_type": kind},
        )

    infraction.refresh_from_db()
    assert infraction.suspension_days == 2
    assert infraction.suspension_type == "internal"


def test_a_resolved_infraction_takes_no_more_votes(client_as, committee, infraction):
    infraction.is_resolved = True
    infraction.save()

    client_as(committee[0]).post(_url(infraction), {"decision": "escalate"})

    assert not BehaviorCommitteeVote.objects.filter(infraction=infraction).exists()


def test_garbage_suspension_input_does_not_crash(client_as, committee, infraction):
    resp = client_as(committee[0]).post(
        _url(infraction),
        {"decision": "suspend", "suspension_days": "abc", "suspension_type": "x" * 50},
    )

    assert resp.status_code == 302
    vote = BehaviorCommitteeVote.objects.get(infraction=infraction)
    assert (vote.suspension_days, vote.suspension_type) == (1, "internal")


def test_the_reporter_cannot_vote_and_the_quorum_is_counted_from_the_rest(
    client_as, committee, infraction
):
    """تضاربُ المصلحة: المُبلِّغُ لا يصوّت، والنصابُ من بقيّة المؤهَّلين (4 ⇒ ثلاثة)."""
    infraction.reported_by = committee[0]
    infraction.save()

    client_as(committee[0]).post(_url(infraction), {"decision": "escalate"})
    assert not BehaviorCommitteeVote.objects.filter(infraction=infraction).exists()

    for member in committee[1:3]:
        client_as(member).post(_url(infraction), {"decision": "escalate"})
    infraction.refresh_from_db()
    assert infraction.level == 3, "اثنان من أربعة لا يكفيان"

    client_as(committee[3]).post(_url(infraction), {"decision": "escalate"})
    infraction.refresh_from_db()
    assert infraction.level == 4

"""إشعارُ العيادة لوليّ الأمر بالحدث لا بالسبب (W-20261020-025، قرار المالك).

سببُ الزيارة والأعراضُ والإجراءُ بياناتٌ صحيّةٌ لقاصر (PDPPL م.8): لا تخرج في بريد وليّ الأمر ولا تُخزَّن
نصّاً صريحاً في سجلّ الإشعارات (`NotificationLog`). يطلبها وليُّ الأمر من الممرّض مباشرةً.
"""

import pytest
from django.core import mail

from clinic.services import ClinicService
from notifications.models import NotificationLog

# قيمٌ فريدةٌ لا تتصادف مع أيّ نصٍّ في القالب: ظهورُ أيٍّ منها في إشعارٍ يعني تسرّب بيانٍ صحّيّ.
SECRETS = ("سببٌ-صحّيٌّ-سرّيٌّ-71", "عَرَضٌ-سرّيٌّ-72", "إجراءٌ-سرّيٌّ-73")


def _record_sent_home(school, student, nurse):
    """زيارةُ إحالةٍ للمنزل بعد تأكيد الممرّض (الإرسالُ لم يعد آليّاً عند التسجيل — W-20261020-034)."""
    reason, symptoms, treatment = SECRETS
    visit = ClinicService.record_visit(
        school=school,
        student=student,
        nurse=nurse,
        reason=reason,
        symptoms=symptoms,
        treatment=treatment,
        is_sent_home=True,
    )
    ClinicService.confirm_referral_notice(visit, school, nurse)
    visit.refresh_from_db()
    return visit


@pytest.mark.django_db
def test_the_sent_home_email_carries_the_event_but_not_the_health_data(
    school, student_user, nurse_user, parent_user
):
    mail.outbox.clear()
    visit = _record_sent_home(school, student_user, nurse_user)

    assert visit.parent_notified is True, "الإشعارُ بالحدث يجب أن يُرسَل"
    assert len(mail.outbox) == 1
    sent = mail.outbox[0]
    assert student_user.full_name in sent.body, "الإشعارُ بالحدث (إرسالُ الطالب للمنزل) باقٍ"
    for secret in SECRETS:
        assert secret not in sent.subject
        assert secret not in sent.body
        assert all(secret not in str(alt) for alt in getattr(sent, "alternatives", []))


@pytest.mark.django_db
def test_no_health_text_is_stored_in_the_notification_log(
    school, student_user, nurse_user, parent_user
):
    _record_sent_home(school, student_user, nurse_user)

    logs = list(NotificationLog.objects.filter(school=school))
    assert logs, "الإشعارُ يُسجَّل في السجلّ"
    for log in logs:
        stored = f"{log.subject} {log.body}"
        for secret in SECRETS:
            assert secret not in stored, f"نصٌّ صحّيٌّ صريحٌ في سجلّ الإشعارات: {secret}"


@pytest.mark.django_db
def test_a_visit_not_sent_home_sends_nothing(school, student_user, nurse_user, parent_user):
    mail.outbox.clear()
    ClinicService.record_visit(
        school=school,
        student=student_user,
        nurse=nurse_user,
        reason=SECRETS[0],
        is_sent_home=False,
    )
    assert mail.outbox == []
    assert not NotificationLog.objects.filter(school=school).exists()

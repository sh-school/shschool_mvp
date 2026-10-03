"""[W-20261002-042] حارسُ المحو يتّسع من حقل `student` إلى كلّ علاقةٍ بالمستخدم.

الطالبُ مستخدمٌ أيضاً: إشعاراتُه ورسائلُه واشتراكاتُه تحمل `user` أو `recipient` لا
`student`، فلم يرها حارسُ `test_erasure_coverage.py`. كلُّ نموذجٍ فيه FK إلى المستخدم
بأحد هذه الأسماء، أو حقلٌ نصّيٌّ يحمل مستلماً/هاتفاً/بريداً، لا بدّ أن يكون:
- في `_lazy_student_fk_models` (يُمحى)، أو
- في `RETAINED` / `STAFF_OR_SYSTEM` أدناه **بسببٍ مكتوب** (يُراجَع مع 0105/DPO).

نموذجٌ جديدٌ لا يدخل أيّاً منها يُسقط هذا الاختبار — فالقرارُ يُتَّخذ لا يُترك للصدفة.
"""

import re

from django.apps import apps
from django.conf import settings

from governance.erasure_service import _lazy_student_fk_models

#: أسماءُ حقولٍ تحمل في العادة المستخدمَ صاحبَ البيانات (لا `created_by` ونحوه).
USER_FIELD_NAMES = {"user", "recipient", "child", "member", "owner", "author", "person"}

#: حقولٌ نصّيّةٌ تحمل هويّةً أو وجهةَ اتّصال.
TEXT_PII = re.compile(
    r"(recipient|student_name|parent_name|phone|email|national_id|guardian)", re.I
)

#: يُحتفَظ بها بعد المحو عمداً — السببُ شرطُ الدخول.
RETAINED = {
    ("core.Profile", "user"): "يُحذف في الخطوة 7 من ErasureService.execute (حذفٌ مخصَّص)",
    ("core.AuditLog", "user"): "سجلُّ التدقيق لا يُمحى (م.19)؛ المستخدمُ مجهَّلٌ فيه",
    ("core.Membership", "user"): "ربطُ مجهَّلٍ بالمدرسة لا يحمل بياناً؛ يُبقي سلامةَ العدّ والإحصاء",
    ("core.CapabilityGrant", "user"): "صلاحيّاتُ كادرٍ لا طلبة",
    ("token_blacklist.OutstandingToken", "user"): (
        "حذفُها يمحو معها قائمةَ الإبطال فقد يصحّ توكنٌ مُبطَلٌ غيرُ منتهٍ؛ "
        "والمستخدمُ المجهَّلُ غيرُ نشطٍ فتُرفض توكناتُه"
    ),
    (
        "developer_feedback.LegalOnboardingConsent",
        "user",
    ): "دليلُ موافقةٍ قانونيّة — قرارُ الاحتفاظ لـ0105/DPO",
    (
        "developer_feedback.DeveloperMessage",
        "user",
    ): "رسائلُ مستخدمٍ إلى المطوّر — قرارُ محوها أو تجهيلها لـ0105/DPO (SET_NULL)",
    ("notifications.NotificationDelivery", "recipient"): (
        "دليلُ محاولة تسليمٍ (PROTECT) — قرارُ الاحتفاظ لـ0105/DPO"
    ),
    ("notifications.NotificationEnqueueIntent", "recipient"): (
        "نيّةُ إرسالٍ دائمة (PROTECT) — قرارُ الاحتفاظ لـ0105/DPO"
    ),
}

#: علاقاتُ كادرٍ أو نظامٍ لا يملكها طالب.
STAFF_OR_SYSTEM = {
    ("admin.LogEntry", "user"): "سجلُّ إجراءات الأدمن (كادر)",
    ("quality.ExecutorMapping", "user"): "خريطةُ منفّذي الجودة (كادر)",
    ("quality.QualityCommitteeMember", "user"): "عضويّةُ لجنة الجودة (كادر)",
    (
        "developer_feedback.DeveloperMessageNotification",
        "recipient",
    ): "مستلمو إشعارات المطوّر (المطوّر)",
    ("transport.SchoolBus", "driver_phone"): "هاتفُ سائقٍ لا طالب",
    ("core.School", "phone"): "هاتفُ المدرسة",
    ("core.School", "email"): "بريدُ المدرسة",
    ("notifications.NotificationSettings", "absence_email_subject"): "قالبُ عنوانٍ لا بياناتُ شخص",
    ("notifications.NotificationSettings", "fail_email_subject"): "قالبُ عنوانٍ لا بياناتُ شخص",
}


def _covered():
    return {Model for Model, _field, _one in _lazy_student_fk_models()}


def _hits():
    user_model = apps.get_model(settings.AUTH_USER_MODEL)
    covered = _covered()
    found = []
    for model in apps.get_models():
        if model in covered or model is user_model:
            continue
        for field in model._meta.concrete_fields:
            is_user_fk = (
                field.is_relation
                and field.related_model is user_model
                and field.name in USER_FIELD_NAMES
            )
            is_text_pii = field.get_internal_type() in {
                "CharField",
                "TextField",
                "EmailField",
            } and bool(TEXT_PII.search(field.name))
            if is_user_fk or is_text_pii:
                found.append((model._meta.label, field.name))
    return found


def test_every_user_relation_is_erased_or_justified():
    known = set(RETAINED) | set(STAFF_OR_SYSTEM)
    unclassified = sorted(hit for hit in _hits() if hit not in known)

    assert unclassified == [], (
        "علاقاتٌ بالمستخدم أو حقولٌ نصّيّةٌ بهويّةٍ لم يُقرَّر مصيرُها في المحو — أضِفها إلى "
        f"_lazy_student_fk_models أو إلى RETAINED/STAFF_OR_SYSTEM بسبب: {unclassified}"
    )


def test_exemptions_do_not_go_stale():
    """استثناءٌ لنموذجٍ حُذف أو دخل المحوَ يُزال من السجلّ."""
    live = set(_hits())
    stale = sorted(k for k in set(RETAINED) | set(STAFF_OR_SYSTEM) if k not in live)

    assert stale == [], f"استثناءاتٌ لم تعد تُطابق شيئاً: {stale}"


def test_every_exemption_has_a_written_reason():
    for registry in (RETAINED, STAFF_OR_SYSTEM):
        for key, reason in registry.items():
            assert reason.strip(), f"{key}: السببُ فارغ"


def test_personal_content_stores_are_erased():
    """مخازنُ محتوى الطالب الشخصيّ تدخل المحو: إشعاراتُه واشتراكاتُه وتفضيلاتُه."""
    covered = {m._meta.label for m in _covered()}

    for label in (
        "notifications.InAppNotification",
        "notifications.PushSubscription",
        "notifications.UserNotificationPreference",
    ):
        assert label in covered, f"{label} لا يُمحى مع الطالب"


import pytest  # noqa: E402

from core.models import ErasureRequest  # noqa: E402
from governance.erasure_service import ErasureService  # noqa: E402

from .conftest import UserFactory  # noqa: E402


@pytest.mark.django_db
def test_user_keyed_notification_rows_are_gone_after_erasure(school, student_user):
    from notifications.models import (
        InAppNotification,
        PushSubscription,
        UserNotificationPreference,
    )

    InAppNotification.objects.create(user=student_user, school=school, title="إشعار")
    PushSubscription.objects.create(
        user=student_user, school=school, endpoint="https://push.example.test/x", p256dh="k"
    )
    UserNotificationPreference.objects.create(user=student_user)
    admin = UserFactory(full_name="مدير", is_superuser=True)
    req = ErasureRequest.objects.create(
        school=school,
        student=student_user,
        requested_by=admin,
        reason="اختبار مخازن user",
        status="approved",
        reviewed_by=admin,
    )

    ErasureService.execute(req)

    assert not InAppNotification.objects.filter(user=student_user).exists()
    assert not PushSubscription.objects.filter(user=student_user).exists()
    assert not UserNotificationPreference.objects.filter(user=student_user).exists()

"""[NOTIFICATIONS] إعدادات الإشعارات: حقلا «موضوع رسالة الغياب/الرسوب» أُزيلا من الشاشة.

السبب: رسائل ولي الأمر صارت بعنوان محايد (#1529)، فلا أثر لهذين الحقلين.
الحقلان باقيان في النموذج والقاعدة (لا هجرة)، لكنّ الشاشة لا تعرضهما،
وحفظُ الإعدادات لا يكتب قيمتهما: تبقى القيمةُ المخزَّنة كما هي.
"""

import pytest
from django.urls import reverse

from notifications.models import NotificationSettings

ABSENCE_SUBJECT = "غياب {student_name}"
FAIL_SUBJECT = "نتيجة {student_name}"


@pytest.fixture
def stored_subjects(school):
    """قيمتان مخزَّنتان معروفتان نتحقّق من بقائهما."""
    NotificationSettings.objects.update_or_create(
        school=school,
        defaults={
            "absence_email_subject": ABSENCE_SUBJECT,
            "fail_email_subject": FAIL_SUBJECT,
        },
    )
    return NotificationSettings.objects.get(school=school)


@pytest.mark.django_db
def test_subject_fields_are_not_rendered_on_settings_screen(
    client, principal_user, stored_subjects
):
    """الحقلان لا يظهران في الشاشة، والقسم يبقى بحدّ الغياب فقط."""
    client.force_login(principal_user)

    response = client.get(reverse("notifications_dashboard"))
    html = response.content.decode()

    assert response.status_code == 200
    assert 'name="absence_email_subject"' not in html
    assert 'name="fail_email_subject"' not in html
    assert "موضوع رسالة الغياب" not in html
    assert "موضوع رسالة الرسوب" not in html
    assert 'name="absence_threshold"' in html
    assert "حدّ الغياب" in html


@pytest.mark.django_db
def test_saving_settings_does_not_change_stored_subjects(client, principal_user, stored_subjects):
    """حفظ الإعدادات بالحقول المعروضة لا يمسّ موضوعَي البريد المخزَّنين."""
    client.force_login(principal_user)

    response = client.post(
        reverse("save_notif_settings"),
        {"absence_threshold": "5", "from_name": "المدرسة"},
    )

    assert response.status_code == 302
    stored_subjects.refresh_from_db()
    assert stored_subjects.absence_email_subject == ABSENCE_SUBJECT
    assert stored_subjects.fail_email_subject == FAIL_SUBJECT
    assert stored_subjects.absence_threshold == 5


@pytest.mark.django_db
def test_saving_settings_ignores_subject_keys_if_posted(client, principal_user, stored_subjects):
    """نموذجٌ قديم مخزَّن في المتصفح قد يرسل الحقلين: يُتجاهلان ولا يُكتبان."""
    client.force_login(principal_user)

    client.post(
        reverse("save_notif_settings"),
        {
            "absence_threshold": "3",
            "absence_email_subject": "قيمة جديدة",
            "fail_email_subject": "قيمة جديدة",
        },
    )

    stored_subjects.refresh_from_db()
    assert stored_subjects.absence_email_subject == ABSENCE_SUBJECT
    assert stored_subjects.fail_email_subject == FAIL_SUBJECT

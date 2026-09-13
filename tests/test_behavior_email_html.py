"""[NOTIFICATIONS] بريدُ السلوك يخرج منسَّقاً — والسلكُ بين القالب والمُرسِل محروس.

كان `notifications/email/behavior_html.html` مكتوباً ولا يستدعيه مُرسِل:
`notify_absence` و`notify_fail` يرندران قالبَيهما ويمرّران `body_html`،
أمّا السلوك فكان يمرّ بالـHub الذي يرسل `body_text` وحدَه. فيصل وليَّ
الأمر أشدُّ الإشعارات حساسيّةً — مخالفةُ ابنه واستدعاؤه — نصّاً عارياً،
بينما يصله تنبيهُ الغياب بترويسة المدرسة.

وهذان الفحصان يحرسان طرفَي السلك: أنّ القالب يرندر بالمفاتيح التي
يبنيها موضعُ الاستدعاء، وأنّ الـHub يمرّر الناتجَ إلى `body_html`.
"""

from types import SimpleNamespace
from unittest.mock import patch

from django.template.loader import render_to_string

TEMPLATE = "notifications/email/behavior_html.html"
TEXT_TEMPLATE = "notifications/email/behavior_text.txt"

#: المفاتيحُ التي يبنيها `BehaviorService.notify_parents` — أسماءٌ مقروءة
#: لا كائنات، فالسياقُ يعبر Celery مُسلسَلاً.
CALL_SITE_CONTEXT = {
    "student_name": "أحمد عبدالله",
    "parent_name": "عبدالله أحمد",
    "school_name": "مدرسة الشحانية",
    "infraction_date": "2026/09/11",
    "level": 2,
    "level_display": "الدرجة الثانية",
    "level_description": "مخالفة متوسّطة",
    "description": "تأخّر متكرّر",
    "action_taken": "إنذار خطّي",
    "reported_by": "سفيان مسيف",
    "points_deducted": 5,
}


def test_the_template_renders_with_what_the_call_site_builds():
    """مفتاحٌ يُعاد تسميتُه في الخدمة يترك فراغاً في بريدٍ يصل وليَّ الأمر."""
    html = render_to_string(TEMPLATE, CALL_SITE_CONTEXT)
    missing = [
        value
        for key, value in CALL_SITE_CONTEXT.items()
        if isinstance(value, str) and value not in html
    ]
    assert not missing, "قيمٌ لم تظهر في البريد: " + ", ".join(missing)
    assert "{{" not in html and "{%" not in html, "وسمٌ لم يُحَلّ في البريد"


def test_the_text_part_renders_too():
    """نظيرُ الـHTML النصّيُّ — بديلُ البريد حين لا يُعرض المنسَّق."""
    text = render_to_string(TEXT_TEMPLATE, CALL_SITE_CONTEXT)
    assert "{{" not in text and "{%" not in text
    assert CALL_SITE_CONTEXT["student_name"] in text
    assert str(CALL_SITE_CONTEXT["points_deducted"]) in text


def test_the_hub_passes_the_rendered_html_to_the_mailer():
    """السلكُ نفسُه: ما يُرندَر يصل `body_html` لا يُهمَل."""
    from notifications import hub

    user = SimpleNamespace(pk=1, email="parent@example.com", full_name="عبدالله أحمد")
    school = SimpleNamespace(id="s1", name="مدرسة الشحانية")

    with patch("notifications.services.NotificationService.send_email") as mailer:
        hub._send_sync(
            user=user,
            school=school,
            channels=["email"],
            title="مخالفة",
            body="نصّ",
            event_type="behavior_l2",
            context={},
            sent_by=None,
            email_html="<b>منسَّق</b>",
            email_text="نصٌّ غنيّ",
        )
    assert mailer.called, "لم يُستدعَ المُرسِل"
    assert mailer.call_args.kwargs.get("body_html") == "<b>منسَّق</b>"
    assert mailer.call_args.kwargs.get("body_text") == "نصٌّ غنيّ"


def test_without_a_template_the_mail_stays_plain():
    """السلوكُ القديم محفوظ: بلا قالبٍ لا `body_html`."""
    from notifications import hub

    user = SimpleNamespace(pk=1, email="parent@example.com", full_name="ولي أمر")
    school = SimpleNamespace(id="s1", name="مدرسة")

    with patch("notifications.services.NotificationService.send_email") as mailer:
        hub._send_sync(
            user=user,
            school=school,
            channels=["email"],
            title="عنوان",
            body="نصّ",
            event_type="general",
            context={},
            sent_by=None,
        )
    assert mailer.call_args.kwargs.get("body_html") is None
    assert mailer.call_args.kwargs.get("body_text") == "نصّ"

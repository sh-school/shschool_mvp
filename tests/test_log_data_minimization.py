"""[B4-7O] لا بيانات شخصية دلالية في سجلّات `notifications`.

القناع لا يُنقذ ما لا شكل له. البريد والهاتف ورقم الهوية تُلتقط بأنماط؛ أمّا
**الاسم وعنوان الإشعار ونصّه** فلا شكل لها — خصوصاً بالعربية. فالحماية الوحيدة
الصادقة ألّا تُكتب أصلاً.

وهذا حارسُ **غيابٍ من المصدر**: يمسح كل نداء تسجيل في الوحدة بالشجرة النحوية،
لا سطراً بعينه. إصلاحُ المثال الأشهر وحده كان سيترك الباب مفتوحاً لأخيه.
"""

import ast
import pathlib

import pytest

from notifications import hub

PACKAGE = pathlib.Path(hub.__file__).parent

#: تعبيراتٌ تُنتج بياناً بشرياً دلالياً حين تُدرَج في رسالة سجلّ.
#:
#: `_name` بالنهاية لا `name` في أي موضع: الأخيرة تلتقط `task_name` و`school_id`
#: ...و`event_name` فتُفقدنا رصداً نافعاً بلا مقابل.
FORBIDDEN_ATTRIBUTES = {
    "full_name",
    "student_name",
    "parent_name",
    "recipient_name",
    "display_name",
    "email",
    "phone",
    "recipient_email",
    "phone_number",
}

#: أسماء متغيّرات تحمل محتوى الإشعار نفسه.
FORBIDDEN_NAMES = {
    "title",
    "subject",
    "body",
    "body_text",
    "body_html",
    "message_text",
    "recipient_email",
    "phone_number",
}


def _log_calls(tree):
    """كل `logger.<level>(...)` في الشجرة."""
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if (
            isinstance(func, ast.Attribute)
            and isinstance(func.value, ast.Name)
            and func.value.id == "logger"
        ):
            yield node


def _leaked_symbols(call):
    """ما يُسرّبه هذا النداء من رموزٍ ممنوعة — أو مجموعة فارغة.

    يفحص الوسائط كلّها، وينزل داخل f-strings: `f"{user.full_name}"` تُدرَج قبل
    أن يراها أي فلتر، فهي أخطر من `%s` لا أقلّ.
    """
    leaked = set()

    for node in ast.walk(call):
        # `user.full_name` أو `alert.student.full_name`
        if isinstance(node, ast.Attribute) and node.attr in FORBIDDEN_ATTRIBUTES:
            leaked.add(node.attr)

        # متغيّرٌ مجرّد اسمه `title` أو `body`
        elif isinstance(node, ast.Name) and node.id in FORBIDDEN_NAMES:
            leaked.add(node.id)

    return leaked


def _source_files():
    return [
        path
        for path in sorted(PACKAGE.rglob("*.py"))
        if "migrations" not in path.parts and path.name != "__init__.py"
    ]


@pytest.mark.parametrize("path", _source_files(), ids=lambda p: p.name)
def test_no_semantic_pii_in_notification_logs(path):
    """لا اسم ولا عنوان ولا نصّ ولا وجهة اتصال في أي نداء تسجيل."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    offenders = []

    for call in _log_calls(tree):
        leaked = _leaked_symbols(call)
        if leaked:
            offenders.append((call.lineno, sorted(leaked)))

    assert offenders == [], (
        f"{path.name}: نداء تسجيل يحمل بياناً بشرياً دلالياً — " f"استبدله بمُعرِّف مبهم: {offenders}"
    )


def test_the_scanner_sees_a_planted_leak():
    """ضبطٌ موجب: حارسٌ لا يلتقط تسريباً مزروعاً لا يحرس شيئاً."""
    planted = ast.parse(
        'logger.info(f"sending to {user.full_name}")\n'
        'logger.warning("subject=%s", title)\n'
        'logger.info("recipient_id=%s", user.pk)\n'
    )

    found = [sorted(_leaked_symbols(call)) for call in _log_calls(planted)]

    assert found == [["full_name"], ["title"], []], found


def test_task_and_school_names_are_not_flagged():
    """ضبطٌ سالب على الحارس نفسه: لا نمسح رصداً نافعاً بمطابقةٍ فضفاضة.

    `name` كمقطعٍ داخل المفتاح كانت ستُسقط `task_name` و`school_name` و
    `event_name` — فنخسر ما يُفيد بلا أن نكسب خصوصية.
    """
    benign = ast.parse(
        'logger.info("task=%s", task_name)\n'
        'logger.info("event=%s", event_name)\n'
        'logger.info("file=%s", filename)\n'
    )

    assert all(not _leaked_symbols(call) for call in _log_calls(benign))

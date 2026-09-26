"""[DBT-11] حمولةُ DLQ قائمةٌ بيضاء — تشخيصٌ لا محتوى، ولا مفتاحَ محتوىً أبداً.

المستودعُ عامّ، والحمولةُ تُقرأ في لوحة الإدارة: فلا بريدَ ولا هاتفَ ولا موضوعَ ولا نصّاً ولا اسماً فيها، بل معرّفاتٌ
ونوعٌ وسببٌ (`notifications/no_provider.py::DLQ_PAYLOAD_KEYS`). وهذا حارسٌ **بنيويّ** على ثلاثة مستويات، فلا يكفي أن
يكون الكاتبون اليومَ نظيفين:

1. الكتابةُ الوحيدة في `DeadLetterMessage` هي `_to_dlq` (لا `create` في موضعٍ آخر) — وهي تُنقّي بالقائمة البيضاء وقتَ الكتابة.
2. كلُّ نداءٍ لـ`_to_dlq` أو `_tracked_failure(payload=…)` في الشيفرة يمرّر **قاموساً حرفيّاً** مفاتيحُه نصوصٌ ثابتةٌ داخل القائمة
   البيضاء — فمفتاحٌ جديدٌ يُضاف يسقط الاختبارُ قبل أن يبلغ القاعدة، وحمولةٌ محسوبةٌ ديناميكيّاً (لا يُعرف مفتاحُها) تسقط كذلك.
3. القائمةُ البيضاءُ نفسُها لا تحمل اسمَ مفتاحِ محتوى.
"""

from __future__ import annotations

import ast
import pathlib

import pytest

from notifications.no_provider import DLQ_PAYLOAD_KEYS, clean_payload

ROOT = pathlib.Path(__file__).resolve().parent.parent

#: أسماءٌ تُعدّ محتوىً أو هويّةً — لا تدخل القائمةَ البيضاء ولا تُكتب في DLQ أبداً.
CONTENT_KEYS = frozenset(
    {
        "recipient_email",
        "email",
        "to",
        "phone",
        "phone_number",
        "recipient",
        "subject",
        "title",
        "body",
        "body_text",
        "body_html",
        "message",
        "text",
        "content",
        "name",
        "full_name",
        "national_id",
        "address",
    }
)


def _sources():
    """كلُّ شيفرة التطبيق (لا الاختبارات ولا الهجرات ولا الأشجار المساعدة)."""
    skip = {"tests", "migrations", ".claude", "node_modules", "venv", ".venv", "staticfiles"}
    for path in ROOT.rglob("*.py"):
        parts = set(path.relative_to(ROOT).parts)
        if parts & skip or any(
            part.startswith(("_", ".")) for part in path.relative_to(ROOT).parts
        ):
            continue
        yield path


def _calls(name):
    """(الملفّ، السطر، عُقدةُ النداء) لكلّ نداءٍ باسمٍ بسيطٍ `name(...)` في شيفرة التطبيق."""
    for path in _sources():
        try:
            tree = ast.parse(path.read_text(encoding="utf-8", errors="ignore"))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id == name
            ):
                yield path.relative_to(ROOT).as_posix(), node.lineno, node


def _payload_arg(call, keyword, position):
    for kw in call.keywords:
        if kw.arg == keyword:
            return kw.value
    return call.args[position] if len(call.args) > position else None


def _literal_keys(node):
    """مفاتيحُ قاموسٍ حرفيّ نصوصُها ثابتة — أو `None` إن لم يكن كذلك (حمولةٌ ديناميكيّة)."""
    if not isinstance(node, ast.Dict):
        return None
    keys = []
    for key in node.keys:
        if not (isinstance(key, ast.Constant) and isinstance(key.value, str)):
            return None
        keys.append(key.value)
    return keys


# ── ١) كاتبٌ واحدٌ ────────────────────────────────────────────────────────


def test_only_the_dlq_writer_creates_dead_letter_rows():
    offenders = []
    for path in _sources():
        text = path.read_text(encoding="utf-8", errors="ignore")
        rel = path.relative_to(ROOT).as_posix()
        if rel in {"notifications/models.py", "notifications/tasks.py"}:
            continue
        if "DeadLetterMessage.objects.create" in text or "DeadLetterMessage(" in text:
            offenders.append(rel)
    assert not offenders, f"كتابةٌ في DLQ خارج `_to_dlq`: {offenders}"


def test_the_dlq_writer_cleans_with_the_whitelist():
    source = (ROOT / "notifications" / "tasks.py").read_text(encoding="utf-8")
    body = source[source.index("def _to_dlq") : source.index("def _tracked_failure")]
    assert "payload=clean_payload(payload)" in body, "`_to_dlq` تُنقّي الحمولةَ بالقائمة البيضاء"
    assert body.count("DeadLetterMessage.objects.create") == 1, "كاتبٌ واحد"


# ── ٢) كلُّ نداءٍ قاموسٌ حرفيٌّ داخل القائمة ─────────────────────────────────────


def test_every_dlq_call_passes_a_literal_payload_inside_the_whitelist():
    checked, problems = 0, []
    for name, keyword, position in (
        ("_to_dlq", "payload", 2),
        ("_tracked_failure", "payload", None),
    ):
        for rel, line, call in _calls(name):
            payload = (
                _payload_arg(call, keyword, position)
                if position is not None
                else next((kw.value for kw in call.keywords if kw.arg == keyword), None)
            )
            if payload is None:
                problems.append(f"{rel}:{line} — {name} بلا حمولةٍ ظاهرة")
                continue
            checked += 1
            # تمريرُ الحمولة من وسيطٍ باسمها داخل `_tracked_failure` نفسِها مقبولٌ: نداءاتُها تُفحص هنا
            if isinstance(payload, ast.Name) and payload.id == "payload" and name == "_to_dlq":
                continue
            keys = _literal_keys(payload)
            if keys is None:
                problems.append(f"{rel}:{line} — حمولةٌ غيرُ حرفيّة (لا يُعرف مفتاحُها قبل التشغيل)")
            else:
                outside = sorted(set(keys) - DLQ_PAYLOAD_KEYS)
                if outside:
                    problems.append(f"{rel}:{line} — مفاتيحُ خارج القائمة البيضاء: {outside}")
    assert checked >= 6, f"الحارسُ لم يقرأ ما يكفي من النداءات ({checked}) — انكسر الكاشف"
    assert not problems, "\n".join(problems)


def test_the_detector_catches_what_it_claims_to_catch():
    good = ast.parse('_to_dlq("email", 1, {"student_id": 1, "notif_type": "x"}, exc)').body[0].value
    bad_key = ast.parse('_to_dlq("email", 1, {"student_id": 1, "subject": "س"}, exc)').body[0].value
    dynamic = ast.parse('_to_dlq("email", 1, build(), exc)').body[0].value
    computed_key = ast.parse('_to_dlq("email", 1, {key: 1}, exc)').body[0].value

    assert set(_literal_keys(_payload_arg(good, "payload", 2))) <= DLQ_PAYLOAD_KEYS
    assert "subject" in _literal_keys(_payload_arg(bad_key, "payload", 2))
    assert _literal_keys(_payload_arg(dynamic, "payload", 2)) is None
    assert _literal_keys(_payload_arg(computed_key, "payload", 2)) is None


# ── ٣) القائمةُ نفسُها ────────────────────────────────────────────────────


def test_the_whitelist_holds_no_content_key():
    assert not (DLQ_PAYLOAD_KEYS & CONTENT_KEYS), sorted(DLQ_PAYLOAD_KEYS & CONTENT_KEYS)
    assert DLQ_PAYLOAD_KEYS, "قائمةٌ فارغةٌ ستمرّ بكلّ شيء — ولا حمولةَ تُكتب"


@pytest.mark.django_db
def test_the_writer_drops_content_keys_at_write_time(school):
    """طبقةُ الدفاع الثانية: لو تسلّل مفتاحُ محتوىً إلى نداءٍ مستقبليّ لم يصل القاعدةَ."""
    from notifications.models import DeadLetterMessage
    from notifications.tasks import _to_dlq

    _to_dlq(
        "email",
        school.id,
        {
            "student_id": "1",
            "notif_type": "custom",
            "recipient_email": "parent@example.com",
            "subject": "موضوعٌ اصطناعيّ",
            "body_text": "نصٌّ اصطناعيّ",
        },
        RuntimeError("x"),
    )

    stored = DeadLetterMessage.objects.get(school=school).payload
    assert set(stored) == {"student_id", "notif_type"}
    assert "parent@example.com" not in str(stored) and "موضوعٌ" not in str(stored)


def test_clean_payload_keeps_the_whitelist_and_logs_only_key_names(caplog):
    import logging

    with caplog.at_level(logging.WARNING):
        cleaned = clean_payload({"user_id": "u1", "body": "نصٌّ سرّيّ", "phone": "+97455555555"})

    assert cleaned == {"user_id": "u1"}
    assert "body" in caplog.text and "phone" in caplog.text
    assert "نصٌّ سرّيّ" not in caplog.text and "+97455555555" not in caplog.text

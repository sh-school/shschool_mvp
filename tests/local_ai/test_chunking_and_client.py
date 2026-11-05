"""[LOCAL-AI] التقطيعُ والعميل — بلا قاعدة بيانات ولا شبكة."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
import requests

from local_ai import chunking
from local_ai.client import (
    LMStudioClient,
    LocalAIDisabledError,
    LocalAIError,
    LocalAIUnavailableError,
    parse_json_object,
    strip_thinking,
)

# ── التقطيع ──────────────────────────────────────────────────────────────


def test_short_text_is_one_chunk():
    assert chunking.split_into_chunks("جملة واحدة قصيرة.") == ["جملة واحدة قصيرة."]


def test_chunks_respect_max_chars_and_sentence_boundaries():
    sentences = [f"هذه الجملة رقم {i} في الوثيقة." for i in range(40)]
    text = " ".join(sentences)
    chunks = chunking.split_into_chunks(text, max_chars=120, overlap=30)
    assert len(chunks) > 3
    assert all(len(c) <= 120 for c in chunks)
    # كلُّ جملةٍ موجودةٌ كاملةً في مقطعٍ ما (لا قطعَ في منتصف جملة).
    joined = "\n".join(chunks)
    assert all(s in joined for s in sentences)


def test_overlap_carries_the_tail_of_the_previous_chunk():
    text = "الأولى هنا. الثانية هنا. الثالثة هنا. الرابعة هنا. الخامسة هنا."
    chunks = chunking.split_into_chunks(text, max_chars=30, overlap=12)
    assert len(chunks) >= 2
    assert chunks[1].startswith(chunks[0].split()[-1]) or chunks[0].split()[-1] in chunks[1]


def test_a_single_oversized_sentence_is_hard_split():
    text = "أ" * 500
    chunks = chunking.split_into_chunks(text, max_chars=200, overlap=20)
    assert [len(c) for c in chunks] == [200, 200, 100]


def test_arabic_question_mark_ends_a_sentence():
    assert chunking.split_sentences("هل حضر؟ نعم حضر.") == ["هل حضر؟", "نعم حضر."]


# ── العميل ───────────────────────────────────────────────────────────────


def test_strip_thinking_removes_think_blocks():
    assert strip_thinking("<think>أفكّر…</think>\nالجواب") == "الجواب"
    assert strip_thinking("بلا تفكير") == "بلا تفكير"


@pytest.mark.parametrize(
    "raw",
    [
        '{"a": 1}',
        'نصّ قبل {"a": 1} ونصّ بعد',
        '```json\n{"a": 1}\n```',
        '<think>…</think>{"a": 1}',
    ],
)
def test_parse_json_object_tolerates_wrappers(raw):
    assert parse_json_object(raw) == {"a": 1}


def test_parse_json_object_refuses_non_objects():
    with pytest.raises(LocalAIError):
        parse_json_object("[1, 2]")


def test_no_think_switch_goes_to_system_message_not_user():
    messages = [{"role": "system", "content": "نظام"}, {"role": "user", "content": "سؤال"}]
    out = LMStudioClient._apply_think_switch(messages, think=False)
    assert out[0]["content"].endswith("/no_think")
    assert out[1]["content"] == "سؤال"
    assert LMStudioClient._apply_think_switch(messages, think=True) == messages


def test_no_think_switch_adds_system_message_when_missing():
    out = LMStudioClient._apply_think_switch([{"role": "user", "content": "س"}], think=False)
    assert out[0] == {"role": "system", "content": "/no_think"}


def _client_with(session: MagicMock) -> LMStudioClient:
    return LMStudioClient(
        base_url="http://127.0.0.1:1234/v1",
        chat_model="m",
        embed_model="e",
        timeout=3,
        enabled=True,
        session=session,
    )


def test_disabled_client_raises_without_touching_the_network():
    session = MagicMock()
    client = LMStudioClient(
        base_url="http://x/v1",
        chat_model="m",
        embed_model="e",
        timeout=3,
        enabled=False,
        session=session,
    )
    with pytest.raises(LocalAIDisabledError):
        client.chat([{"role": "user", "content": "س"}])
    session.post.assert_not_called()
    assert client.health()["ok"] is False


def test_connection_error_becomes_unavailable():
    session = MagicMock()
    session.post.side_effect = requests.ConnectionError("refused")
    with pytest.raises(LocalAIUnavailableError):
        _client_with(session).chat([{"role": "user", "content": "س"}])


def test_chat_parses_content_and_strips_thinking():
    session = MagicMock()
    session.post.return_value = MagicMock(
        status_code=200,
        json=lambda: {
            "model": "m",
            "choices": [{"message": {"content": "<think>x</think>مرحباً", "tool_calls": None}}],
            "usage": {"total_tokens": 7},
        },
    )
    result = _client_with(session).chat([{"role": "user", "content": "س"}])
    assert result.content == "مرحباً"
    assert result.usage["total_tokens"] == 7
    payload = session.post.call_args.kwargs["json"]
    assert payload["stream"] is False and payload["model"] == "m"


def test_embed_checks_vector_count():
    session = MagicMock()
    session.post.return_value = MagicMock(
        status_code=200, json=lambda: {"data": [{"index": 0, "embedding": [1, 0]}]}
    )
    with pytest.raises(LocalAIError):
        _client_with(session).embed(["أ", "ب"])
    assert _client_with(session).embed([]) == []


def test_chat_stream_yields_deltas_and_skips_think_blocks():
    lines = [
        'data: {"choices":[{"delta":{"content":"<think>سرّ"}}]}',
        'data: {"choices":[{"delta":{"content":"</think>أه"}}]}',
        'data: {"choices":[{"delta":{"content":"لاً"}}]}',
        "data: [DONE]",
    ]
    response = MagicMock(status_code=200)
    response.iter_lines.return_value = iter(lines)
    session = MagicMock()
    session.post.return_value = response
    assert "".join(_client_with(session).chat_stream([{"role": "user", "content": "س"}])) == "أهلاً"

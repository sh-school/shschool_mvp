"""مثبّتاتُ اختبارات local_ai — عميلٌ مزيَّفٌ محلُّ LM Studio، فلا اختبارَ يطلب شبكةً.

`fake_ai` يستبدل طرقَ `LMStudioClient` (تضمينٌ حتميٌّ من الكلمات، محادثةٌ معلَّبة، صحّةٌ موجبة)
ويفعّل `LOCAL_AI_ENABLED`؛ فالبحثُ الدلاليّ يُختبر فعليّاً: متّجهُ الاستعلام يقترب من المقطع الذي
يشاركه كلماتٍ أكثر.
"""

from __future__ import annotations

import json
import zlib
from typing import Any

import pytest

from local_ai import client as client_module
from local_ai.client import ChatResult, LMStudioClient

DIMS = 64


def keyword_embedding(text: str) -> list[float]:
    """متّجهٌ حتميٌّ: كلُّ كلمةٍ تزيد خانةً (hash % 64) — يكفي لاختبار الترتيب بجيب التمام."""
    vector = [0.0] * DIMS
    for word in text.lower().split():
        vector[zlib.crc32(word.encode("utf-8")) % DIMS] += 1.0
    norm = sum(v * v for v in vector) ** 0.5 or 1.0
    return [v / norm for v in vector]


class FakeAI:
    """يسجّل الاستدعاءات ويتيح للاختبار تحديدَ ردّ المحادثة التالي."""

    def __init__(self) -> None:
        self.chat_calls: list[dict[str, Any]] = []
        self.embed_calls: list[list[str]] = []
        self.next_reply: str = "ردٌّ مزيَّف [1]"
        self.next_json: dict[str, Any] | None = None

    def embed(self, _client, texts: list[str], *, model: str | None = None) -> list[list[float]]:
        self.embed_calls.append(list(texts))
        return [keyword_embedding(t) for t in texts]

    def chat(self, _client, messages: list[dict[str, Any]], **kwargs: Any) -> ChatResult:
        self.chat_calls.append({"messages": messages, **kwargs})
        if kwargs.get("response_format") and self.next_json is not None:
            return ChatResult(content=json.dumps(self.next_json, ensure_ascii=False))
        return ChatResult(content=self.next_reply)

    def health(self, _client) -> dict[str, Any]:
        return {"ok": True, "models": ["qwen/qwen3-8b", "text-embedding-bge-m3"], "error": ""}


@pytest.fixture
def fake_ai(monkeypatch, settings) -> FakeAI:
    settings.LOCAL_AI_ENABLED = True
    settings.LOCAL_AI_BASE_URL = "http://127.0.0.1:1234/v1"
    settings.LOCAL_AI_CHAT_MODEL = "qwen/qwen3-8b"
    settings.LOCAL_AI_EMBED_MODEL = "text-embedding-bge-m3"
    settings.LOCAL_AI_TIMEOUT = 5
    fake = FakeAI()
    monkeypatch.setattr(
        LMStudioClient,
        "embed",
        lambda self, texts, model=None: fake.embed(self, texts, model=model),
    )
    monkeypatch.setattr(
        LMStudioClient, "chat", lambda self, messages, **kw: fake.chat(self, messages, **kw)
    )
    monkeypatch.setattr(LMStudioClient, "health", lambda self: fake.health(self))
    monkeypatch.setattr(client_module, "_default_client", None)
    return fake

"""عميلُ LM Studio — واجهةٌ متوافقةٌ مع OpenAI على الجهاز المحلّيّ، بلا مكتبةٍ خارجيّة.

يعتمد على `requests` (موجودةٌ في المتطلّبات) لا على حزمة `openai`، كي لا تدخل حزمةٌ
جديدةٌ صورةَ الإنتاج لميزةٍ اختياريّة. كلُّ الإعدادات من `settings.LOCAL_AI_*`:

- `LOCAL_AI_ENABLED`      — المفتاحُ العامّ؛ معطَّلٌ افتراضاً، فالمنصّةُ تعمل بلا نموذج.
- `LOCAL_AI_BASE_URL`     — `http://127.0.0.1:1234/v1` (خادمُ LM Studio).
- `LOCAL_AI_CHAT_MODEL`   — معرِّفُ نموذج المحادثة (مثل `qwen/qwen3-8b`).
- `LOCAL_AI_EMBED_MODEL`  — معرِّفُ نموذج التضمين (مثل `text-embedding-bge-m3`).
- `LOCAL_AI_TIMEOUT`      — مهلةُ الطلب بالثواني.

الأخطاء: `LocalAIDisabledError` حين المفتاحُ مطفأ، و`LocalAIUnavailableError` حين الخادمُ لا يجيب،
و`LocalAIError` لأيّ ردٍّ غير صالح. الاستدعاءاتُ متزامنةٌ وقصيرة؛ الطويلُ منها (الفهرسة) في Celery.
"""

from __future__ import annotations

import json
import logging
import re
from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Any

import requests
from django.conf import settings

logger = logging.getLogger(__name__)

_THINK_BLOCK = re.compile(r"<think>.*?</think>\s*", re.DOTALL)
#: إيقافُ مرحلة التفكير في نماذج Qwen3 (مفتاحٌ ناعمٌ تفهمه من نصّ الرسالة).
NO_THINK_SWITCH = "/no_think"


class LocalAIError(RuntimeError):
    """ردٌّ غيرُ صالحٍ من الخادم المحلّيّ."""


class LocalAIDisabledError(LocalAIError):
    """`LOCAL_AI_ENABLED` مطفأ."""


class LocalAIUnavailableError(LocalAIError):
    """خادمُ LM Studio لا يجيب (مغلقٌ أو النموذجُ غيرُ محمَّل)."""


@dataclass(frozen=True)
class ChatResult:
    content: str
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    usage: dict[str, int] = field(default_factory=dict)
    model: str = ""


def strip_thinking(text: str) -> str:
    """يحذف كتلَ `<think>…</think>` إن أرجعها النموذجُ داخل المحتوى."""
    return _THINK_BLOCK.sub("", text or "").strip()


class LMStudioClient:
    """عميلٌ خفيفٌ: `chat` و`chat_stream` و`embed` و`chat_json` و`health`."""

    def __init__(
        self,
        base_url: str | None = None,
        chat_model: str | None = None,
        embed_model: str | None = None,
        timeout: int | None = None,
        enabled: bool | None = None,
        session: requests.Session | None = None,
    ) -> None:
        self.base_url = (base_url or settings.LOCAL_AI_BASE_URL).rstrip("/")
        self.chat_model = chat_model or settings.LOCAL_AI_CHAT_MODEL
        self.embed_model = embed_model or settings.LOCAL_AI_EMBED_MODEL
        self.timeout = timeout or settings.LOCAL_AI_TIMEOUT
        self.enabled = settings.LOCAL_AI_ENABLED if enabled is None else enabled
        self._session = session or requests.Session()

    # ── أساسيّات ───────────────────────────────────────────────────────

    def is_enabled(self) -> bool:
        return bool(self.enabled)

    def _require_enabled(self) -> None:
        if not self.is_enabled():
            raise LocalAIDisabledError("الذكاءُ المحلّيّ معطَّل (LOCAL_AI_ENABLED=false).")

    def _post(
        self, path: str, payload: dict[str, Any], *, stream: bool = False
    ) -> requests.Response:
        self._require_enabled()
        url = f"{self.base_url}{path}"
        try:
            response = self._session.post(url, json=payload, timeout=self.timeout, stream=stream)
        except requests.ConnectionError as exc:
            raise LocalAIUnavailableError(f"تعذّر الوصول إلى LM Studio على {self.base_url}") from exc
        except requests.Timeout as exc:
            raise LocalAIUnavailableError(
                f"انتهت مهلةُ الطلب ({self.timeout}s) إلى LM Studio"
            ) from exc
        if response.status_code >= 400:
            raise LocalAIError(f"LM Studio أعاد {response.status_code}: {response.text[:300]}")
        return response

    def health(self) -> dict[str, Any]:
        """يعيد `{"ok": bool, "models": [...], "error": str}` بلا استثناءٍ — للفحص واللوحات."""
        if not self.is_enabled():
            return {"ok": False, "models": [], "error": "معطَّل"}
        try:
            response = self._session.get(f"{self.base_url}/models", timeout=min(self.timeout, 10))
            response.raise_for_status()
            models = [m.get("id", "") for m in response.json().get("data", [])]
            return {"ok": True, "models": models, "error": ""}
        except (requests.RequestException, ValueError) as exc:
            return {"ok": False, "models": [], "error": str(exc)}

    # ── المحادثة ───────────────────────────────────────────────────────

    @staticmethod
    def _apply_think_switch(messages: list[dict[str, Any]], think: bool) -> list[dict[str, Any]]:
        """يلحق `/no_think` برسالة النظام (أو يضيف واحدةً) حين لا نريد تفكيراً — بلا تغيير رسالة المستخدم."""
        if think:
            return messages
        out = [dict(m) for m in messages]
        for m in out:
            if m.get("role") == "system":
                if NO_THINK_SWITCH not in str(m.get("content", "")):
                    m["content"] = f"{m.get('content', '')}\n{NO_THINK_SWITCH}".strip()
                return out
        return [{"role": "system", "content": NO_THINK_SWITCH}, *out]

    def chat(
        self,
        messages: list[dict[str, Any]],
        *,
        model: str | None = None,
        temperature: float = 0.3,
        max_tokens: int = 1024,
        tools: list[dict[str, Any]] | None = None,
        response_format: dict[str, Any] | None = None,
        think: bool = False,
    ) -> ChatResult:
        payload: dict[str, Any] = {
            "model": model or self.chat_model,
            "messages": self._apply_think_switch(messages, think),
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": False,
        }
        if tools:
            payload["tools"] = tools
        if response_format:
            payload["response_format"] = response_format
        data = self._post("/chat/completions", payload).json()
        try:
            message = data["choices"][0]["message"]
        except (KeyError, IndexError, TypeError) as exc:
            raise LocalAIError(f"ردٌّ غيرُ متوقَّع من LM Studio: {str(data)[:300]}") from exc
        return ChatResult(
            content=strip_thinking(message.get("content") or ""),
            tool_calls=list(message.get("tool_calls") or []),
            usage=dict(data.get("usage") or {}),
            model=str(data.get("model") or payload["model"]),
        )

    def chat_stream(
        self,
        messages: list[dict[str, Any]],
        *,
        model: str | None = None,
        temperature: float = 0.3,
        max_tokens: int = 1024,
        think: bool = False,
    ) -> Iterator[str]:
        """يولّد مقاطعَ النصّ تباعاً (SSE) — للواجهات التي تعرض الردَّ وهو يُكتب."""
        payload = {
            "model": model or self.chat_model,
            "messages": self._apply_think_switch(messages, think),
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": True,
        }
        response = self._post("/chat/completions", payload, stream=True)
        inside_think = False
        for raw in response.iter_lines(decode_unicode=True):
            if not raw or not raw.startswith("data:"):
                continue
            chunk = raw[5:].strip()
            if chunk == "[DONE]":
                break
            try:
                delta = json.loads(chunk)["choices"][0]["delta"].get("content") or ""
            except (ValueError, KeyError, IndexError, TypeError):
                continue
            # كتلُ التفكير قد تأتي مقطَّعةً عبر عدّة deltas — نحذفها بآلة حالةٍ بسيطة.
            if "<think>" in delta:
                inside_think = True
                delta = delta.split("<think>", 1)[0]
            if inside_think:
                if "</think>" in delta:
                    inside_think = False
                    delta = delta.split("</think>", 1)[1]
                else:
                    continue
            if delta:
                yield delta

    def chat_json(
        self,
        messages: list[dict[str, Any]],
        schema: dict[str, Any],
        *,
        schema_name: str = "result",
        temperature: float = 0.0,
        max_tokens: int = 1024,
    ) -> dict[str, Any]:
        """ردٌّ مقيَّدٌ بـJSON Schema (يدعمه LM Studio) مع احتياطٍ يلتقط أوّلَ كائن JSON في النصّ."""
        response_format = {
            "type": "json_schema",
            "json_schema": {"name": schema_name, "strict": True, "schema": schema},
        }
        result = self.chat(
            messages,
            temperature=temperature,
            max_tokens=max_tokens,
            response_format=response_format,
        )
        return parse_json_object(result.content)

    # ── التضمين ────────────────────────────────────────────────────────

    def embed(self, texts: list[str], *, model: str | None = None) -> list[list[float]]:
        """متّجهٌ لكلّ نصّ، بترتيب الإدخال. القائمةُ الفارغة تعيد فارغة بلا طلب."""
        if not texts:
            return []
        payload = {"model": model or self.embed_model, "input": texts}
        data = self._post("/embeddings", payload).json()
        try:
            items = sorted(data["data"], key=lambda d: d.get("index", 0))
            vectors = [list(map(float, item["embedding"])) for item in items]
        except (KeyError, TypeError, ValueError) as exc:
            raise LocalAIError(f"ردُّ تضمينٍ غيرُ صالح: {str(data)[:300]}") from exc
        if len(vectors) != len(texts):
            raise LocalAIError(f"عددُ المتّجهات {len(vectors)} لا يساوي عددَ النصوص {len(texts)}")
        return vectors


def parse_json_object(text: str) -> dict[str, Any]:
    """يحلّل JSON من ردّ النموذج: كاملاً، أو من داخل سياج ```json، أو أوّلَ `{…}` فيه."""
    text = strip_thinking(text)
    candidates = [text]
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if fenced:
        candidates.append(fenced.group(1))
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end > start:
        candidates.append(text[start : end + 1])
    for candidate in candidates:
        try:
            parsed = json.loads(candidate)
        except ValueError:
            continue
        if isinstance(parsed, dict):
            return parsed
    raise LocalAIError(f"لم يُعِد النموذجُ كائنَ JSON صالحاً: {text[:200]}")


_default_client: LMStudioClient | None = None


def get_client() -> LMStudioClient:
    """عميلٌ مشتركٌ بإعدادات المشروع (يُعاد بناؤه عند تغيّر الإعدادات في الاختبارات)."""
    global _default_client
    wanted = (
        settings.LOCAL_AI_BASE_URL,
        settings.LOCAL_AI_CHAT_MODEL,
        settings.LOCAL_AI_EMBED_MODEL,
        settings.LOCAL_AI_ENABLED,
    )
    current = _default_client
    if current is None or (
        current.base_url.rstrip("/") != wanted[0].rstrip("/")
        or current.chat_model != wanted[1]
        or current.embed_model != wanted[2]
        or current.enabled != wanted[3]
    ):
        _default_client = LMStudioClient()
    return _default_client

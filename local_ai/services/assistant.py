"""مساعدُ المحادثة داخل المنصّة — يجيب من وثائق المدرسة أوّلاً، ثمّ معرفةً عامّةً بحدود الدور.

الخصوصيّة بالبنية (PDPPL): المساعدُ لا يملك أدواتٍ تقرأ سجلّات الطلبة، وسياقُه الوحيد مقاطعُ
وثائق المعرفة التي رفعتها القيادة. فحتى لو سأل موظّفٌ عن طالبٍ بعينه يعتذر المساعدُ ويحيله
إلى صفحة الطالب في المنصّة. والمحادثةُ تُحفظ في جلسة المستخدم (آخر `HISTORY_LIMIT` أدوار)
لا في قاعدة البيانات، فلا أثرَ لها بعد الخروج.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from local_ai.client import LMStudioClient, get_client
from local_ai.services import rag

HISTORY_LIMIT = 10
MESSAGE_MAX_CHARS = 2000

GENERAL_SYSTEM_PROMPT = """أنت «مساعد المدرسة» داخل منصّة SchoolOS لموظّفي مدرسةٍ قطريّة.
- أجب بالعربيّة الفصحى المبسّطة وباختصار، والخلاصةُ أوّلاً.
- لا تطّلع على سجلّات الطلبة ولا تملك أدواتٍ لذلك؛ إن سُئلت عن طالبٍ أو وليّ أمرٍ أو موظّفٍ بعينه
  فاعتذر وأحِل السائلَ إلى صفحته في المنصّة.
- ما تعرفه من وثائق المدرسة يأتيك كمقاطعَ مرجعيّة؛ أشر إليها بأرقامها [1] [2]. وما ليس فيها
  أجب عنه معرفةً عامّةً مع قول «هذه معلومةٌ عامّة لا من وثائق المدرسة».
- لا تخترع سياساتٍ أو مواعيدَ أو أرقاماً."""


@dataclass(frozen=True)
class AssistantReply:
    text: str
    sources: list[rag.Hit] = field(default_factory=list)
    used_documents: bool = False


def _trim_history(history: list[dict[str, str]] | None) -> list[dict[str, str]]:
    turns = [
        {"role": t["role"], "content": str(t["content"])[:MESSAGE_MAX_CHARS]}
        for t in (history or [])
        if t.get("role") in ("user", "assistant") and t.get("content")
    ]
    return turns[-HISTORY_LIMIT:]


def respond(
    *,
    school: Any,
    message: str,
    history: list[dict[str, str]] | None = None,
    client: LMStudioClient | None = None,
) -> AssistantReply:
    """دورٌ واحد: يبحث في الوثائق، ويضيف ما وجد إلى السياق، ويطلب الردّ."""
    client = client or get_client()
    message = (message or "").strip()[:MESSAGE_MAX_CHARS]
    if not message:
        return AssistantReply(text="اكتب سؤالك أوّلاً.", sources=[], used_documents=False)

    hits = rag.search(school, message, client=client) if school is not None else []
    messages: list[dict[str, str]] = [{"role": "system", "content": GENERAL_SYSTEM_PROMPT}]
    messages.extend(_trim_history(history))
    if hits:
        user_content = f"المقاطع المرجعيّة من وثائق المدرسة:\n{rag.build_context(hits)}\n\nسؤال الموظّف: {message}"
    else:
        user_content = message
    messages.append({"role": "user", "content": user_content})
    result = client.chat(messages, temperature=0.3, max_tokens=700)
    return AssistantReply(text=result.content, sources=hits, used_documents=bool(hits))

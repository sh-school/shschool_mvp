"""RAG محلّيّ — فهرسةُ وثائق المعرفة وبحثٌ دلاليٌّ بالعربيّة وإجابةٌ مسنَدةٌ بمراجع.

- `index_document(doc)`: نصٌّ → مقاطعُ → متّجهاتٌ (bge-m3) → `DocumentChunk`؛ يحدّث حالةَ الوثيقة.
- `search(school, query, k)`: أقربُ المقاطع بجيب التمام ضمن وثائق المدرسة المفعَّلة الجاهزة.
- `answer(school, question, history)`: يبني سياقاً من أفضل المقاطع ويطلب من النموذج إجابةً
  لا تخرج عنه، مع أرقام المراجع `[1]`، `[2]`… التي تُعرض للمستخدم.

الحسابُ في NumPy على مصفوفةٍ تُبنى عند كلّ طلب: بضعةُ آلاف مقطعٍ × 1024 بُعداً = عشراتُ
الميغابايت في الذاكرة لأجزاءٍ من الثانية؛ أكثرُ من ذلك يستدعي pgvector (الواجهةُ نفسُها تبقى).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

import numpy as np
from django.db import transaction
from django.utils import timezone

from local_ai.chunking import split_into_chunks
from local_ai.client import LMStudioClient, LocalAIError, get_client
from local_ai.models import DocumentChunk, KnowledgeDocument
from local_ai.text_extraction import UnsupportedDocumentError, extract_text

logger = logging.getLogger(__name__)

EMBED_BATCH = 16
DEFAULT_TOP_K = 5
#: أقلُّ تشابهٍ يُعدّ معه المقطعُ ذا صلة (bge-m3 يعطي ~0.3 للنصوص غير المرتبطة، و>0.5 للمرتبطة).
MIN_SCORE = 0.35


class IndexingError(RuntimeError):
    """فشلت الفهرسةُ — الرسالةُ محفوظةٌ في `KnowledgeDocument.error_message` أيضاً."""


@dataclass(frozen=True)
class Hit:
    chunk_id: int
    document_id: str
    title: str
    ordinal: int
    text: str
    score: float


@dataclass(frozen=True)
class Answer:
    text: str
    hits: list[Hit] = field(default_factory=list)

    @property
    def grounded(self) -> bool:
        return bool(self.hits)


# ── التضمين والفهرسة ──────────────────────────────────────────────────


def embed_texts(texts: list[str], *, client: LMStudioClient | None = None) -> list[list[float]]:
    """تضمينٌ على دفعاتٍ صغيرة كي لا يطول طلبٌ واحد على خادمٍ محلّيّ."""
    client = client or get_client()
    vectors: list[list[float]] = []
    for start in range(0, len(texts), EMBED_BATCH):
        vectors.extend(client.embed(texts[start : start + EMBED_BATCH]))
    return vectors


def index_document(doc: KnowledgeDocument, *, client: LMStudioClient | None = None) -> int:
    """يفهرس الوثيقةَ كاملةً ويعيد عددَ المقاطع. يسجّل الفشلَ على الوثيقة ثمّ يرفع `IndexingError`."""
    client = client or get_client()
    doc.status = KnowledgeDocument.Status.INDEXING
    doc.error_message = ""
    doc.save(update_fields=["status", "error_message", "updated_at"])
    try:
        with doc.file.open("rb") as stream:
            text = extract_text(stream, doc.filename or doc.file.name)
        chunks = split_into_chunks(text)
        if not chunks:
            raise UnsupportedDocumentError("لم ينتج عن الملفّ أيُّ مقطع.")
        vectors = embed_texts(chunks, client=client)
    except (UnsupportedDocumentError, LocalAIError, OSError) as exc:
        doc.mark_failed(str(exc))
        raise IndexingError(str(exc)) from exc

    with transaction.atomic():
        DocumentChunk.objects.filter(document=doc).delete()
        DocumentChunk.objects.bulk_create(
            [
                DocumentChunk(
                    school_id=doc.school_id,
                    document=doc,
                    ordinal=i,
                    text=chunk,
                    char_count=len(chunk),
                    embedding=vector,
                )
                for i, (chunk, vector) in enumerate(zip(chunks, vectors, strict=True))
            ],
            batch_size=200,
        )
        doc.status = KnowledgeDocument.Status.READY
        doc.chunk_count = len(chunks)
        doc.indexed_at = timezone.now()
        doc.save(update_fields=["status", "chunk_count", "indexed_at", "updated_at"])
    return len(chunks)


# ── البحث ───────────────────────────────────────────────────────────────


def _cosine_scores(matrix: np.ndarray, query: np.ndarray) -> np.ndarray:
    norms = np.linalg.norm(matrix, axis=1) * (np.linalg.norm(query) or 1.0)
    norms[norms == 0] = 1.0
    return (matrix @ query) / norms


def search(
    school: Any,
    query: str,
    *,
    k: int = DEFAULT_TOP_K,
    min_score: float = MIN_SCORE,
    client: LMStudioClient | None = None,
) -> list[Hit]:
    """أقربُ `k` مقاطعَ لسؤالٍ ضمن وثائق المدرسة الجاهزة المفعَّلة (بترتيب التشابه تنازليّاً)."""
    query = (query or "").strip()
    if not query:
        return []
    rows = list(
        DocumentChunk.objects.filter(
            school=school,
            document__is_active=True,
            document__status=KnowledgeDocument.Status.READY,
        ).values_list("id", "document_id", "document__title", "ordinal", "text", "embedding")
    )
    if not rows:
        return []
    client = client or get_client()
    query_vector = np.asarray(client.embed([query])[0], dtype=np.float32)
    matrix = np.asarray([row[5] for row in rows], dtype=np.float32)
    if matrix.ndim != 2 or matrix.shape[1] != query_vector.shape[0]:
        logger.warning(
            "local_ai.search: أبعادُ التضمين غيرُ متّسقة — أعد الفهرسة بنموذج التضمين الحاليّ"
        )
        return []
    scores = _cosine_scores(matrix, query_vector)
    order = np.argsort(-scores)[: max(k, 0)]
    hits: list[Hit] = []
    for idx in order:
        score = float(scores[idx])
        if score < min_score:
            continue
        chunk_id, document_id, title, ordinal, text, _ = rows[int(idx)]
        hits.append(Hit(chunk_id, str(document_id), title, ordinal, text, round(score, 4)))
    return hits


# ── الإجابة المسنَدة ───────────────────────────────────────────────────

RAG_SYSTEM_PROMPT = """أنت مساعدٌ لموظّفي مدرسةٍ قطريّة. أجب بالعربيّة الفصحى المبسّطة وباختصار.
اعتمد في إجابتك على «المقاطع المرجعيّة» المرفقة فقط، وأشر إلى كلّ معلومةٍ برقم مرجعها بين قوسين مثل [1].
إن لم تكفِ المراجع للإجابة فقل ذلك صراحةً ولا تخمّن. لا تذكر بياناتٍ شخصيّةً لطلبة أو موظّفين."""


def build_context(hits: list[Hit]) -> str:
    return "\n\n".join(
        f"[{i}] ({hit.title} — مقطع {hit.ordinal + 1})\n{hit.text}" for i, hit in enumerate(hits, 1)
    )


def answer(
    school: Any,
    question: str,
    *,
    history: list[dict[str, str]] | None = None,
    k: int = DEFAULT_TOP_K,
    client: LMStudioClient | None = None,
) -> Answer:
    """إجابةٌ مسنَدة: إن لم يُعثر على مقاطعَ ذاتِ صلة يُعاد ردٌّ صريحٌ بذلك بلا استدعاء النموذج."""
    client = client or get_client()
    hits = search(school, question, k=k, client=client)
    if not hits:
        return Answer(text="لم أجد في وثائق المدرسة المفهرَسة ما يجيب عن هذا السؤال.", hits=[])
    messages: list[dict[str, str]] = [{"role": "system", "content": RAG_SYSTEM_PROMPT}]
    for turn in (history or [])[-6:]:
        if turn.get("role") in ("user", "assistant") and turn.get("content"):
            messages.append({"role": turn["role"], "content": turn["content"]})
    messages.append(
        {
            "role": "user",
            "content": f"المقاطع المرجعيّة:\n{build_context(hits)}\n\nالسؤال: {question}",
        }
    )
    result = client.chat(messages, temperature=0.2, max_tokens=700)
    return Answer(text=result.content, hits=hits)

"""أتمتةُ الذكاء المحلّيّ (Celery):

- `local_ai.index_document`          — عند رفع وثيقةٍ أو طلب إعادة فهرستها (مهمّةُ مستأجرٍ واحد).
- `local_ai.enrich_document`         — بعد الفهرسة: بطاقةُ الوثيقة (ملخّصٌ وبياناتٌ منظَّمة).
- `local_ai.index_pending_documents` — مسحٌ مجدوَل (Beat) يلتقط ما بقي بانتظار الفهرسة أو فشل
  حين كان الخادمُ مطفأً، مدرسةً مدرسةً بنطاق RLS — فالنموذجُ المحلّيّ قد لا يكون شغّالاً وقتَ الرفع.

كلُّ مهمّةٍ تعيد قاموسَ أرقامٍ صغيراً يُقرأ في سجلّ العامل، ولا تُسقط مهمّةٌ غيرَها.
"""

from __future__ import annotations

import logging
from typing import Any

from celery import shared_task

from core.celery_tasks import TenantRLSTask, school_rls_scope
from local_ai.beat import local_ai_beat  # noqa: F401 — يبقى متاحًا من هنا للتوافق
from local_ai.client import LocalAIDisabledError, LocalAIError, LocalAIUnavailableError, get_client
from local_ai.models import KnowledgeDocument
from local_ai.services import rag, structured

logger = logging.getLogger(__name__)


def _ready() -> bool:
    """لا طلبَ إلى الخادم حين المفتاحُ مطفأ — المهمّةُ تعود بهدوء وتُعاد في المسح التالي."""
    return get_client().is_enabled()


@shared_task(name="local_ai.index_document", base=TenantRLSTask)
def index_document_task(document_id: str, school_id: str) -> dict[str, Any]:
    """يفهرس وثيقةً واحدة ثمّ يُثري بطاقتها. الفشلُ يُسجَّل على الوثيقة ولا يرفع استثناءً."""
    if not _ready():
        return {"document": document_id, "skipped": "disabled"}
    try:
        doc = KnowledgeDocument.objects.get(pk=document_id, school_id=school_id)
    except KnowledgeDocument.DoesNotExist:
        return {"document": document_id, "skipped": "missing"}
    try:
        count = rag.index_document(doc)
    except rag.IndexingError as exc:
        logger.warning("local_ai.index_document: فشلت فهرسةُ %s — %s", document_id, exc)
        return {"document": document_id, "chunks": 0, "error": str(exc)[:200]}
    enrich_document_task.delay(document_id=document_id, school_id=school_id)
    return {"document": document_id, "chunks": count}


@shared_task(name="local_ai.enrich_document", base=TenantRLSTask)
def enrich_document_task(document_id: str, school_id: str) -> dict[str, Any]:
    """بطاقةُ الوثيقة من أوّل مقاطعها: ملخّصٌ وبياناتٌ منظَّمة — إثراءٌ اختياريٌّ لا يُفشل الفهرسة."""
    if not _ready():
        return {"document": document_id, "skipped": "disabled"}
    try:
        doc = KnowledgeDocument.objects.get(pk=document_id, school_id=school_id)
    except KnowledgeDocument.DoesNotExist:
        return {"document": document_id, "skipped": "missing"}
    text = "\n\n".join(doc.chunks.order_by("ordinal").values_list("text", flat=True)[:8])
    if not text:
        return {"document": document_id, "skipped": "no_chunks"}
    try:
        card = structured.document_card(text)
    except (LocalAIError, ValueError) as exc:
        logger.info("local_ai.enrich_document: تعذّر الإثراءُ لـ%s — %s", document_id, exc)
        return {"document": document_id, "enriched": False, "error": str(exc)[:200]}
    doc.summary = str(card.get("summary") or "")[:2000]
    doc.metadata = card
    doc.save(update_fields=["summary", "metadata", "updated_at"])
    return {"document": document_id, "enriched": True}


@shared_task(name="local_ai.index_pending_documents")
def index_pending_documents_task(include_failed: bool = True) -> dict[str, int]:
    """مسحٌ مجدوَل: يفهرس ما بقي `pending` (و`failed` إن طُلب) مدرسةً مدرسةً بنطاق RLS."""
    from core.models import School

    if not _ready():
        return {"indexed": 0, "failed": 0, "skipped_disabled": 1}
    statuses = [KnowledgeDocument.Status.PENDING]
    if include_failed:
        statuses.append(KnowledgeDocument.Status.FAILED)
    indexed = failed = 0
    for school in School.objects.filter(is_active=True).iterator(chunk_size=100):
        try:
            with school_rls_scope(school.id):
                docs = KnowledgeDocument.objects.filter(
                    school=school, status__in=statuses, is_active=True
                )
                for doc in docs.iterator(chunk_size=50):
                    try:
                        rag.index_document(doc)
                        indexed += 1
                        enrich_document_task.delay(
                            document_id=str(doc.id), school_id=str(school.id)
                        )
                    except rag.IndexingError:
                        failed += 1
                    except (LocalAIDisabledError, LocalAIUnavailableError):
                        logger.warning(
                            "local_ai.index_pending: الخادمُ غيرُ متاح — يُستأنف في المسح التالي"
                        )
                        return {"indexed": indexed, "failed": failed, "unavailable": 1}
        except Exception:  # noqa: BLE001 — مدرسةٌ معطوبةٌ لا تُسقط غيرَها
            failed += 1
            logger.exception("local_ai.index_pending: تعذّر في المدرسة %s", school.pk)
    return {"indexed": indexed, "failed": failed}

"""[LOCAL-AI] الفهرسةُ والبحثُ الدلاليّ والإجابةُ المسنَدة، والأتمتة (مهامّ Celery الفوريّة في الاختبار)."""

from __future__ import annotations

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from local_ai.client import LocalAIError
from local_ai.models import DocumentChunk, KnowledgeDocument
from local_ai.services import assistant, rag, structured
from local_ai.tasks import index_document_task, index_pending_documents_task, local_ai_beat

pytestmark = pytest.mark.django_db

POLICY_TEXT = (
    "سياسة الحضور: يُسجَّل الغياب قبل الحصة الثانية. "
    "موعد تسليم الخطط الفصلية هو الأسبوع الثاني من الفصل الدراسي. "
    "تعميم النقل: حافلات المدرسة تنطلق الساعة السابعة صباحاً من الموقف الشرقي. "
    "سياسة المكتبة: مدة استعارة الكتاب أسبوعان قابلة للتجديد مرة واحدة."
)


def _document(
    school, *, title="سياسات المدرسة", text=POLICY_TEXT, name="policy.txt"
) -> KnowledgeDocument:
    return KnowledgeDocument.objects.create(
        school=school, title=title, file=SimpleUploadedFile(name, text.encode("utf-8"))
    )


# ── الفهرسة ───────────────────────────────────────────────────────────────


def test_index_document_creates_chunks_and_marks_ready(school, fake_ai):
    doc = _document(school)
    count = rag.index_document(doc)
    doc.refresh_from_db()
    assert count == doc.chunk_count == DocumentChunk.objects.filter(document=doc).count() >= 1
    assert doc.status == KnowledgeDocument.Status.READY
    assert doc.indexed_at is not None
    assert all(c.school_id == school.id for c in doc.chunks.all())


def test_reindex_replaces_old_chunks(school, fake_ai):
    doc = _document(school)
    rag.index_document(doc)
    first_ids = set(doc.chunks.values_list("id", flat=True))
    rag.index_document(doc)
    assert set(doc.chunks.values_list("id", flat=True)).isdisjoint(first_ids)
    assert doc.chunks.count() == doc.chunk_count


def test_unsupported_file_is_marked_failed(school, fake_ai):
    doc = _document(school, name="scan.xlsx", text="x" * 50)
    with pytest.raises(rag.IndexingError):
        rag.index_document(doc)
    doc.refresh_from_db()
    assert doc.status == KnowledgeDocument.Status.FAILED
    assert "غير" in doc.error_message


# ── البحث والإجابة ────────────────────────────────────────────────────────


def test_search_ranks_the_matching_chunk_first_and_scopes_to_school(school, fake_ai, monkeypatch):
    from tests.conftest import SchoolFactory

    # كلُّ جملةٍ مقطعٌ مستقلّ (النصُّ أقصر من حجم المقطع الافتراضيّ فنقسمه قسراً لاختبار الترتيب).
    monkeypatch.setattr(
        rag, "split_into_chunks", lambda text, **kw: [s for s in text.split(". ") if s.strip()]
    )
    doc = _document(school)
    rag.index_document(doc)
    assert doc.chunks.count() == 4
    hits = rag.search(school, "موعد تسليم الخطط الفصلية", k=3, min_score=0.0)
    assert hits and "الخطط الفصلية" in hits[0].text
    assert hits[0].title == doc.title
    assert rag.search(SchoolFactory(), "موعد تسليم الخطط الفصلية", min_score=0.0) == []


def test_search_ignores_inactive_or_unready_documents(school, fake_ai):
    doc = _document(school)
    rag.index_document(doc)
    doc.is_active = False
    doc.save(update_fields=["is_active"])
    assert rag.search(school, "الحضور", min_score=0.0) == []


def test_answer_without_hits_does_not_call_the_model(school, fake_ai):
    result = rag.answer(school, "ما لون السماء؟")
    assert not result.grounded and "لم أجد" in result.text
    assert fake_ai.chat_calls == []


def test_answer_with_hits_sends_context_and_system_prompt(school, fake_ai):
    rag.index_document(_document(school))
    fake_ai.next_reply = "موعدُ التسليم الأسبوعُ الثاني [1]."
    result = rag.answer(school, "متى تسليم الخطط؟")
    assert result.grounded and result.text.startswith("موعدُ")
    sent = fake_ai.chat_calls[-1]["messages"]
    assert sent[0]["role"] == "system" and "المقاطع المرجعيّة" in sent[-1]["content"]
    assert "الخطط الفصلية" in sent[-1]["content"]


def test_assistant_respond_uses_documents_and_keeps_history_bounded(school, fake_ai):
    rag.index_document(_document(school))
    history = [{"role": "user", "content": f"س{i}"} for i in range(30)]
    reply = assistant.respond(school=school, message="متى تنطلق الحافلات؟", history=history)
    assert reply.used_documents and reply.sources
    sent = fake_ai.chat_calls[-1]["messages"]
    # نظام + آخر HISTORY_LIMIT أدوار + الرسالةُ الحاليّة
    assert len(sent) == 1 + assistant.HISTORY_LIMIT + 1


def test_assistant_empty_message_short_circuits(school, fake_ai):
    reply = assistant.respond(school=school, message="   ")
    assert reply.text == "اكتب سؤالك أوّلاً." and fake_ai.chat_calls == []


# ── الاستخراجُ المنظَّم ──────────────────────────────────────────────────


def test_document_card_returns_schema_fields(fake_ai):
    fake_ai.next_json = {
        "title": "تعميم الحضور",
        "kind": "circular",
        "issuer": "إدارة المدرسة",
        "date": "2026-09-01",
        "audience": ["المعلّمون"],
        "summary": "يُسجَّل الغياب قبل الحصة الثانية.",
        "deadlines": [{"what": "تسليم الخطط", "when": "الأسبوع الثاني"}],
        "action_items": ["تسجيل الغياب"],
    }
    card = structured.document_card(POLICY_TEXT)
    assert card["kind"] == "circular" and card["deadlines"][0]["what"] == "تسليم الخطط"
    assert fake_ai.chat_calls[-1]["response_format"]["type"] == "json_schema"


def test_missing_required_field_is_an_error(fake_ai):
    fake_ai.next_json = {"title": "فقط"}
    with pytest.raises(LocalAIError):
        structured.document_card(POLICY_TEXT)


def test_classify_constrains_labels(fake_ai):
    fake_ai.next_json = {"label": "شكوى", "confidence": 0.9, "reason": "لهجة اعتراض"}
    out = structured.classify("لم يصل الباص اليوم", ["شكوى", "استفسار", "شكر"])
    assert out["label"] == "شكوى"
    schema = fake_ai.chat_calls[-1]["response_format"]["json_schema"]["schema"]
    assert schema["properties"]["label"]["enum"] == ["شكوى", "استفسار", "شكر"]


# ── الأتمتة ───────────────────────────────────────────────────────────────


def test_index_task_indexes_then_enriches(school, fake_ai):
    doc = _document(school)
    fake_ai.next_json = {
        "title": "سياسات",
        "kind": "policy",
        "issuer": "",
        "date": "",
        "audience": [],
        "summary": "ملخّصٌ تلقائيّ",
        "deadlines": [],
        "action_items": [],
    }
    result = index_document_task.delay(document_id=str(doc.id), school_id=str(school.id)).get()
    doc.refresh_from_db()
    assert result["chunks"] >= 1 and doc.status == KnowledgeDocument.Status.READY
    assert doc.summary == "ملخّصٌ تلقائيّ" and doc.metadata["kind"] == "policy"


def test_index_task_requires_school_id():
    # بلا school_id يُرفض الطلب: TypeError من فحص توقيع Celery عند الإرسال،
    # أو ValueError من TenantRLSTask إن تجاوز الفحص — كلاهما رفضٌ صحيح.
    with pytest.raises((TypeError, ValueError)):
        index_document_task.delay(document_id="x").get()


def test_pending_sweep_indexes_pending_and_retries_failed(school, fake_ai):
    pending = _document(school, title="معلّق")
    failed = _document(school, title="فشل سابقاً")
    failed.mark_failed("الخادم كان مطفأً")
    ready = _document(school, title="جاهز")
    rag.index_document(ready)
    before = fake_ai.embed_calls.copy()
    result = index_pending_documents_task(include_failed=True)
    assert result["indexed"] == 2 and result["failed"] == 0
    assert KnowledgeDocument.objects.filter(status=KnowledgeDocument.Status.READY).count() == 3
    assert len(fake_ai.embed_calls) > len(before)
    pending.refresh_from_db()
    assert pending.error_message == ""


def test_sweep_is_a_noop_when_disabled(school, fake_ai, settings):
    _document(school)
    settings.LOCAL_AI_ENABLED = False
    assert index_pending_documents_task() == {"indexed": 0, "failed": 0, "skipped_disabled": 1}


def test_beat_schedule_names_and_tasks():
    beat = local_ai_beat()
    assert set(beat) == {"local-ai-index-pending-hourly", "local-ai-retry-failed-nightly"}
    assert all(entry["task"] == "local_ai.index_pending_documents" for entry in beat.values())
    assert beat["local-ai-retry-failed-nightly"]["kwargs"] == {"include_failed": True}

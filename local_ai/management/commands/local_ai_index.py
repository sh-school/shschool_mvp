"""`manage.py local_ai_index` — فهرسةٌ يدويّةٌ فوريّة (بلا Celery): ما ينتظر، أو الكلّ، أو مدرسةٌ بعينها."""

from __future__ import annotations

from django.core.management.base import BaseCommand

from core.celery_tasks import school_rls_scope
from core.models import School
from local_ai.models import KnowledgeDocument
from local_ai.services import rag, structured


class Command(BaseCommand):
    help = "فهرسةُ وثائق المعرفة في النموذج المحلّيّ (بانتظار الفهرسة افتراضاً)"

    def add_arguments(self, parser):
        parser.add_argument("--all", action="store_true", help="أعد فهرسةَ كلّ الوثائق المفعَّلة")
        parser.add_argument("--school", help="رمزُ مدرسةٍ واحدة (code)")
        parser.add_argument("--no-enrich", action="store_true", help="بلا بطاقةِ وثيقةٍ تلقائيّة")

    def handle(self, *args, **options):
        schools = School.objects.filter(is_active=True)
        if options["school"]:
            schools = schools.filter(code=options["school"])
        statuses = (
            None
            if options["all"]
            else [KnowledgeDocument.Status.PENDING, KnowledgeDocument.Status.FAILED]
        )
        done = failed = 0
        for school in schools.iterator(chunk_size=50):
            with school_rls_scope(school.id):
                docs = KnowledgeDocument.objects.filter(school=school, is_active=True)
                if statuses:
                    docs = docs.filter(status__in=statuses)
                for doc in docs.iterator(chunk_size=50):
                    try:
                        count = rag.index_document(doc)
                    except rag.IndexingError as exc:
                        failed += 1
                        self.stdout.write(self.style.ERROR(f"✗ {school.code} / {doc.title}: {exc}"))
                        continue
                    done += 1
                    self.stdout.write(
                        self.style.SUCCESS(f"✓ {school.code} / {doc.title}: {count} مقطعاً")
                    )
                    if not options["no_enrich"]:
                        text = "\n\n".join(doc.chunks.values_list("text", flat=True)[:8])
                        try:
                            card = structured.document_card(text)
                        except Exception as exc:  # noqa: BLE001 — الإثراءُ اختياريّ
                            self.stdout.write(f"  (بلا بطاقة: {exc})")
                            continue
                        doc.summary = str(card.get("summary") or "")[:2000]
                        doc.metadata = card
                        doc.save(update_fields=["summary", "metadata", "updated_at"])
        self.stdout.write(f"تمّ: {done} · فشل: {failed}")

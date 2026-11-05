from django.contrib import admin

from local_ai.models import DocumentChunk, KnowledgeDocument


@admin.register(KnowledgeDocument)
class KnowledgeDocumentAdmin(admin.ModelAdmin):
    list_display = (
        "title",
        "school",
        "status",
        "chunk_count",
        "is_active",
        "indexed_at",
        "created_at",
    )
    list_filter = ("status", "is_active", "school")
    search_fields = ("title",)
    readonly_fields = (
        "status",
        "error_message",
        "summary",
        "metadata",
        "chunk_count",
        "indexed_at",
    )
    ordering = ("-created_at",)


@admin.register(DocumentChunk)
class DocumentChunkAdmin(admin.ModelAdmin):
    list_display = ("document", "ordinal", "char_count")
    list_select_related = ("document",)
    search_fields = ("text",)
    readonly_fields = ("school", "document", "ordinal", "text", "char_count", "embedding")

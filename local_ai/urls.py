"""مساراتُ الذكاء المحلّيّ — `/ai/` (المساعد لكلّ موظّف) و`/ai/documents/` (القيادة)."""

from __future__ import annotations

from django.urls import path

from local_ai import views

app_name = "local_ai"

urlpatterns = [
    path("", views.assistant_page, name="assistant"),
    path("message/", views.assistant_message, name="assistant_message"),
    path("clear/", views.assistant_clear, name="assistant_clear"),
    path("documents/", views.documents, name="documents"),
    path("documents/<uuid:pk>/reindex/", views.document_reindex, name="document_reindex"),
    path("documents/<uuid:pk>/toggle/", views.document_toggle, name="document_toggle"),
]

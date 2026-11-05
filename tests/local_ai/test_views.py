"""[LOCAL-AI] العروض: الحمايةُ (موظّفٌ للمساعد، قيادةٌ للوثائق)، ودورُ HTMX، ورفعُ وثيقةٍ يطلق الفهرسةَ تلقائيّاً."""

from __future__ import annotations

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse

from local_ai.models import KnowledgeDocument
from local_ai.views import SESSION_KEY

pytestmark = pytest.mark.django_db

HX = {"HTTP_HX_REQUEST": "true"}


# ── الحماية ───────────────────────────────────────────────────────────────


def test_anonymous_is_sent_to_login(client):
    response = client.get(reverse("local_ai:assistant"))
    assert response.status_code == 302 and "login" in response["Location"]


def test_staff_reaches_the_assistant(client_as, teacher_user, fake_ai):
    response = client_as(teacher_user).get(reverse("local_ai:assistant"))
    assert response.status_code == 200
    assert "مساعد المدرسة" in response.content.decode()


def test_documents_page_is_for_leadership_only(client_as, teacher_user, principal_user, fake_ai):
    assert client_as(teacher_user).get(reverse("local_ai:documents")).status_code == 403
    assert client_as(principal_user).get(reverse("local_ai:documents")).status_code == 200


def test_message_requires_post(client_as, teacher_user, fake_ai):
    assert client_as(teacher_user).get(reverse("local_ai:assistant_message")).status_code == 405


# ── المحادثة ──────────────────────────────────────────────────────────────


def test_htmx_turn_returns_partial_and_stores_history(client_as, teacher_user, fake_ai):
    fake_ai.next_reply = "الحافلاتُ تنطلق السابعة."
    client = client_as(teacher_user)
    response = client.post(
        reverse("local_ai:assistant_message"), {"message": "متى الحافلات؟"}, **HX
    )
    body = response.content.decode()
    assert response.status_code == 200
    assert "متى الحافلات؟" in body and "الحافلاتُ تنطلق السابعة." in body
    assert "<html" not in body.lower()  # جزءٌ لا صفحة
    history = client.session[SESSION_KEY]
    assert [t["role"] for t in history] == ["user", "assistant"]


def test_service_error_is_shown_but_not_remembered(client_as, teacher_user, fake_ai, monkeypatch):
    from local_ai.client import LocalAIUnavailableError

    def boom(self, messages, **kwargs):
        raise LocalAIUnavailableError("down")

    monkeypatch.setattr("local_ai.client.LMStudioClient.chat", boom)
    client = client_as(teacher_user)
    response = client.post(reverse("local_ai:assistant_message"), {"message": "س"}, **HX)
    assert response.status_code == 200 and 'role="alert"' in response.content.decode()
    assert SESSION_KEY not in client.session


def test_non_htmx_post_redirects_back(client_as, teacher_user, fake_ai):
    response = client_as(teacher_user).post(reverse("local_ai:assistant_message"), {"message": "س"})
    assert response.status_code == 302 and response["Location"] == reverse("local_ai:assistant")


def test_clear_wipes_the_session_history(client_as, teacher_user, fake_ai):
    client = client_as(teacher_user)
    client.post(reverse("local_ai:assistant_message"), {"message": "س"}, **HX)
    assert SESSION_KEY in client.session
    client.post(reverse("local_ai:assistant_clear"))
    assert SESSION_KEY not in client.session


def test_blank_message_is_rejected(client_as, teacher_user, fake_ai):
    response = client_as(teacher_user).post(
        reverse("local_ai:assistant_message"), {"message": "  "}, **HX
    )
    assert "اكتب سؤالاً" in response.content.decode() and fake_ai.chat_calls == []


# ── الوثائق والأتمتة ─────────────────────────────────────────────────────


def test_upload_creates_document_and_indexes_it_immediately(
    client_as, principal_user, school, fake_ai
):
    fake_ai.next_json = {
        "title": "تعميم",
        "kind": "circular",
        "issuer": "",
        "date": "",
        "audience": [],
        "summary": "ملخّص",
        "deadlines": [],
        "action_items": [],
    }
    upload = SimpleUploadedFile(
        "circular.txt", ("تعميم الحضور: يُسجَّل الغياب قبل الحصة الثانية. " * 3).encode()
    )
    response = client_as(principal_user).post(
        reverse("local_ai:documents"), {"title": "تعميم الحضور", "file": upload}, follow=True
    )
    assert response.status_code == 200
    doc = KnowledgeDocument.objects.get(school=school, title="تعميم الحضور")
    assert doc.status == KnowledgeDocument.Status.READY  # Celery فوريٌّ في الاختبار
    assert doc.chunk_count >= 1 and doc.summary == "ملخّص"
    assert doc.uploaded_by == principal_user


def test_upload_rejects_unsupported_extension(client_as, principal_user, school, fake_ai):
    upload = SimpleUploadedFile("grades.xlsx", b"x" * 100)
    response = client_as(principal_user).post(
        reverse("local_ai:documents"), {"title": "كشف", "file": upload}
    )
    assert response.status_code == 200 and "غيرُ مدعوم" in response.content.decode()
    assert not KnowledgeDocument.objects.filter(school=school).exists()


def test_reindex_and_toggle_are_scoped_to_the_school(client_as, principal_user, school, fake_ai):
    from tests.conftest import SchoolFactory

    other = KnowledgeDocument.objects.create(
        school=SchoolFactory(),
        title="أخرى",
        file=SimpleUploadedFile("o.txt", b"other school text here"),
    )
    mine = KnowledgeDocument.objects.create(
        school=school, title="لي", file=SimpleUploadedFile("m.txt", b"my school text here ok")
    )
    client = client_as(principal_user)
    assert client.post(reverse("local_ai:document_toggle", args=[other.pk])).status_code == 404
    client.post(reverse("local_ai:document_toggle", args=[mine.pk]))
    mine.refresh_from_db()
    assert mine.is_active is False
    client.post(reverse("local_ai:document_reindex", args=[mine.pk]))
    mine.refresh_from_db()
    assert mine.status == KnowledgeDocument.Status.READY  # الفهرسةُ الفوريّة نجحت

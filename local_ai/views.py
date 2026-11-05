"""عروضُ الذكاء المحلّيّ — مساعدُ المحادثة (لكلّ موظّف) وإدارةُ وثائق المعرفة (للقيادة).

المحادثةُ في جلسة المستخدم لا في قاعدة البيانات (آخر `HISTORY_LIMIT` أدوار)؛ ومع HTMX يُعاد
الدورُ الجديد وحدَه (`_turn.html`) فيُلحَق بسجلّ المحادثة بلا إعادة تحميل. بلا HTMX تعمل الصفحةُ
بالتحويل العاديّ (تحسينٌ تدريجيّ).
"""

from __future__ import annotations

import logging

from django.contrib import messages
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_GET, require_POST

from core.permissions import leadership_required, staff_required
from local_ai.client import LocalAIDisabledError, LocalAIError, LocalAIUnavailableError, get_client
from local_ai.forms import AssistantMessageForm, DocumentUploadForm
from local_ai.models import KnowledgeDocument
from local_ai.services import assistant
from local_ai.tasks import index_document_task

logger = logging.getLogger(__name__)

SESSION_KEY = "local_ai_history"

UNAVAILABLE_TEXT = (
    "المساعدُ المحلّيّ غيرُ متاحٍ الآن (خادمُ النموذج مطفأ). جرّب لاحقاً أو أبلغ مطوّر المنصّة."
)
DISABLED_TEXT = "المساعدُ المحلّيّ معطَّلٌ في إعدادات المنصّة."


def _history(request: HttpRequest) -> list[dict[str, str]]:
    history = request.session.get(SESSION_KEY) or []
    return [t for t in history if isinstance(t, dict) and t.get("role") and t.get("content")]


def _remember(request: HttpRequest, role: str, content: str) -> None:
    history = _history(request)
    history.append({"role": role, "content": content[: assistant.MESSAGE_MAX_CHARS]})
    request.session[SESSION_KEY] = history[-assistant.HISTORY_LIMIT :]
    request.session.modified = True


def _reply_for(request: HttpRequest, message: str) -> tuple[assistant.AssistantReply, bool]:
    """يعيد (الردّ، هل هو خطأُ خدمةٍ لا إجابةٌ) — فلا يُحفظ الخطأُ في سجلّ المحادثة."""
    try:
        reply = assistant.respond(school=request.school, message=message, history=_history(request))
        return reply, False
    except LocalAIDisabledError:
        return assistant.AssistantReply(text=DISABLED_TEXT), True
    except LocalAIUnavailableError:
        return assistant.AssistantReply(text=UNAVAILABLE_TEXT), True
    except LocalAIError as exc:
        logger.warning("local_ai.assistant: %s", exc)
        return assistant.AssistantReply(text="تعذّر توليدُ الردّ. أعد المحاولة بصياغةٍ أخرى."), True


# ── المساعد ─────────────────────────────────────────────────────────────


@staff_required
@require_GET
def assistant_page(request: HttpRequest) -> HttpResponse:
    health = get_client().health()
    return render(
        request,
        "local_ai/assistant.html",
        {
            "form": AssistantMessageForm(),
            "history": _history(request),
            "ai_ok": health["ok"],
            "ai_error": health["error"],
            "documents_count": KnowledgeDocument.objects.filter(
                school=request.school, is_active=True, status=KnowledgeDocument.Status.READY
            ).count()
            if request.school
            else 0,
        },
    )


@staff_required
@require_POST
def assistant_message(request: HttpRequest) -> HttpResponse:
    form = AssistantMessageForm(request.POST)
    if not form.is_valid():
        if request.htmx:
            return render(
                request, "local_ai/_turn.html", {"error_text": "اكتب سؤالاً من حرفٍ إلى 2000 حرف."}
            )
        messages.error(request, "اكتب سؤالاً من حرفٍ إلى 2000 حرف.")
        return redirect("local_ai:assistant")

    message = form.cleaned_data["message"].strip()
    reply, is_error = _reply_for(request, message)
    if not is_error:
        _remember(request, "user", message)
        _remember(request, "assistant", reply.text)

    context = {"user_text": message, "reply": reply, "error_text": reply.text if is_error else ""}
    if request.htmx:
        return render(request, "local_ai/_turn.html", context)
    if is_error:
        messages.error(request, reply.text)
    return redirect("local_ai:assistant")


@staff_required
@require_POST
def assistant_clear(request: HttpRequest) -> HttpResponse:
    request.session.pop(SESSION_KEY, None)
    request.session.modified = True
    return redirect("local_ai:assistant")


# ── وثائق المعرفة (القيادة) ───────────────────────────────────────────


@leadership_required
def documents(request: HttpRequest) -> HttpResponse:
    if request.school is None:
        messages.error(request, "لا مدرسةَ مرتبطةً بحسابك.")
        return redirect("dashboard")
    if request.method == "POST":
        form = DocumentUploadForm(request.POST, request.FILES)
        if form.is_valid():
            doc = KnowledgeDocument.objects.create(
                school=request.school,
                title=form.cleaned_data["title"],
                file=form.cleaned_data["file"],
                uploaded_by=request.user,
            )
            index_document_task.delay(document_id=str(doc.id), school_id=str(request.school.id))
            messages.success(request, f"رُفعت «{doc.title}» وبدأت فهرستُها في الخلفيّة.")
            return redirect("local_ai:documents")
    else:
        form = DocumentUploadForm()
    docs = KnowledgeDocument.objects.filter(school=request.school).select_related("uploaded_by")
    return render(
        request,
        "local_ai/documents.html",
        {"form": form, "documents": docs, "ai_ok": get_client().health()["ok"]},
    )


@leadership_required
@require_POST
def document_reindex(request: HttpRequest, pk: str) -> HttpResponse:
    doc = get_object_or_404(KnowledgeDocument, pk=pk, school=request.school)
    doc.status = KnowledgeDocument.Status.PENDING
    doc.error_message = ""
    doc.save(update_fields=["status", "error_message", "updated_at"])
    index_document_task.delay(document_id=str(doc.id), school_id=str(doc.school_id))
    messages.info(request, f"أُعيدت «{doc.title}» إلى طابور الفهرسة.")
    return redirect("local_ai:documents")


@leadership_required
@require_POST
def document_toggle(request: HttpRequest, pk: str) -> HttpResponse:
    doc = get_object_or_404(KnowledgeDocument, pk=pk, school=request.school)
    doc.is_active = not doc.is_active
    doc.save(update_fields=["is_active", "updated_at"])
    messages.info(request, f"«{doc.title}» {'مفعَّلة' if doc.is_active else 'موقوفة'} الآن.")
    return redirect("local_ai:documents")

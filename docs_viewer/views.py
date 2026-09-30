"""عارضُ md المركزيّ — فهرسٌ (`/docs/`) وصفحةُ عرضٍ (`/docs/<مسار>/`)، لمطوّر المنصّة وحدَه.

W-20260930-002: لا عارضَ مركزيّاً لملفّات md في المشروع (بما فيها `.claude/`)؛
هذا التطبيقُ يقرأ الملفَّ حيّاً من القرص عند كلّ طلبٍ — لا تخزينَ ولا فهرسةً مسبقة.
"""

from __future__ import annotations

from django.http import HttpRequest, HttpResponse
from django.shortcuts import render
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET

from core.developer_access import developer_only
from docs_viewer import services
from docs_viewer.rendering import render_markdown


@developer_only
@require_GET
@never_cache
def index(request: HttpRequest) -> HttpResponse:
    """فهرسُ `/docs/` — شجرةُ ملفّات md تحت جذر المشروع (نمط `layout-hub`)."""
    tree = services.build_tree()
    return render(request, "docs_viewer/index.html", {"tree": tree})


@developer_only
@require_GET
@never_cache
def detail(request: HttpRequest, doc_path: str) -> HttpResponse:
    """عرضُ ملفٍّ واحد (نمط `layout-report`) — `services.safe_resolve` يحرس المسار."""
    file_path = services.safe_resolve(doc_path)
    text = file_path.read_text(encoding="utf-8", errors="replace")
    rendered = render_markdown(text)
    rel_path = file_path.relative_to(services.DOCS_ROOT).as_posix()
    return render(
        request,
        "docs_viewer/detail.html",
        {
            "doc_path": rel_path,
            "title": file_path.name,
            "content_html": rendered.content_html,
            "toc_html": rendered.toc_html,
            "has_toc": rendered.has_toc,
            # الشجرةُ الجانبيّة (قرارُ المالك ب+ج): التصفّحُ بين الملفّات بلا رجوعٍ لـ/docs/
            "tree": services.build_tree(),
        },
    )

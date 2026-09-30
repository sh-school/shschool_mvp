"""عارضُ md المركزيّ — فهرسٌ (`/docs/`) وصفحةُ عرضٍ (`/docs/<مسار>/`)، لمطوّر المنصّة وحدَه.

W-20260930-002: لا عارضَ مركزيّاً لملفّات md في المشروع (بما فيها `.claude/`)؛
هذا التطبيقُ يقرأ الملفَّ حيّاً من القرص عند كلّ طلبٍ — لا تخزينَ ولا فهرسةً مسبقة.
"""

from __future__ import annotations

import mimetypes

from django.http import FileResponse, HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET

from core.developer_access import developer_only
from docs_viewer import services
from docs_viewer.rendering import render_markdown

#: الملفّ الافتراضيّ عند فتح `/docs/` بلا مسار — طلبُ المالك: الشجرةُ حاضرةٌ من
#: أوّل زيارة، لا صفحةُ اختيارٍ فارغة (README.md موجودٌ دائماً في جذر المشروع).
DEFAULT_DOC = "README.md"


@developer_only
@require_GET
@never_cache
def index(request: HttpRequest) -> HttpResponse:
    """`/docs/` — يحوِّل إلى `DEFAULT_DOC` بالشبكة الثلاثيّة نفسِها (`detail`)، أو
    فهرسٍ بسيطٍ إن غاب الملفُّ الافتراضيّ استثناءً (شجرةٌ فقط، بلا محتوًى مفتوح)."""
    if (services.DOCS_ROOT / DEFAULT_DOC).is_file():
        return redirect("docs_viewer:detail", doc_path=DEFAULT_DOC)
    tree = services.build_tree()
    # الحالةُ الافتراضيّةُ مطويّة (ملاحظةُ المالك) — لا ملفَّ حاليّاً يفتح مجلّداتٍ هنا.
    return render(request, "docs_viewer/index.html", {"tree": tree, "open_dirs": set()})


@developer_only
@require_GET
@never_cache
def detail(request: HttpRequest, doc_path: str) -> HttpResponse:
    """عرضُ ملفٍّ واحد (نمط `layout-report`) — `services.safe_resolve` يحرس المسار."""
    file_path = services.safe_resolve(doc_path)
    text = file_path.read_text(encoding="utf-8", errors="replace")
    rel_path = file_path.relative_to(services.DOCS_ROOT).as_posix()
    # صورُ الملفّ (شعاراتٌ غالباً) تُشار إليها نسبيّاً إلى مجلّده — تُحسَب من هنا
    # لا من داخل render_markdown، فيبقى التصييرُ بلا معرفةٍ بمواضع الملفّات.
    source_dir = rel_path.rsplit("/", 1)[0] if "/" in rel_path else ""
    rendered = render_markdown(text, source_dir=source_dir)

    return render(
        request,
        "docs_viewer/detail.html",
        {
            "doc_path": rel_path,
            # عنوانُ العرض من أوّل عنوان md في الملفّ (طلبُ المالك: يعبّر عن
            # المحتوى لا عن اسم الملفّ الخام)، واسمُ الملفّ الحقيقيّ للفرعيّ.
            "title": services.extract_title(text, fallback=file_path.name),
            "filename": file_path.name,
            "content_html": rendered.content_html,
            # الشجرةُ الجانبيّة (قرارُ المالك ب+ج): التصفّحُ بين الملفّات بلا رجوعٍ لـ/docs/
            "tree": services.build_tree(),
            # الحالةُ الافتراضيّةُ مطويّة (ملاحظةُ المالك) — تُفتح سلسلةُ مجلّدات
            # الملفّ الحاليّ وحدَها.
            "open_dirs": services.ancestor_dirs(rel_path),
        },
    )


@developer_only
@require_GET
@never_cache
def asset(request: HttpRequest, rel_path: str) -> HttpResponse:
    """صورةُ ملفّ md (شعارٌ غالباً) — `services.resolve_asset` يحرس المسارَ
    والامتداد؛ الرابطَ يبنيه `docs_viewer/rendering.py` عند تصيير الصور النسبيّة."""
    file_path = services.resolve_asset(rel_path)
    content_type, _ = mimetypes.guess_type(file_path.name)
    return FileResponse(
        file_path.open("rb"), content_type=content_type or "application/octet-stream"
    )

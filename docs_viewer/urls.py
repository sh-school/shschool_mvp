"""مساراتُ عارض md — لمطوّر المنصّة وحدَه (`core.developer_access.developer_only` في العروض)."""

from __future__ import annotations

from django.urls import path, re_path

from docs_viewer import views

app_name = "docs_viewer"

urlpatterns = [
    path("", views.index, name="index"),
    # صورُ md المُشار إليها بمسارٍ نسبيٍّ (شعاراتٌ غالباً) — بادئةٌ مميَّزةٌ فلا
    # تتصادم مع `.+\.md` أدناه (`docs_viewer/rendering.py` يبني هذا الرابط).
    path("_asset/<path:rel_path>", views.asset, name="asset"),
    # بحثُ المحتوى (JSON) — بادئةٌ مميَّزةٌ أخرى لا تتصادم مع `.+\.md` أدناه.
    path("_search/", views.search, name="search"),
    # `.+` لا `path:` وحدَه: يلزم امتدادَ .md في نهاية الرابط نفسِه (لا شرطة بلا امتداد)
    re_path(r"^(?P<doc_path>.+\.md)/?$", views.detail, name="detail"),
]

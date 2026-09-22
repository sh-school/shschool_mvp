"""مسارات خارطة التجويد — لمطوّر المنصّة وحدَه (`core.developer_access.developer_only`).

أسماءٌ بلا فضاءِ أسماء: `improvement_roadmap` كـ`ui_components` (دليلُ الهويّة) — كلاهما
من «أدوات المطوّر».
"""

from django.urls import path

from roadmap import views

urlpatterns = [
    path("", views.improvement_roadmap, name="improvement_roadmap"),
    path("items/new/", views.item_create, name="roadmap_item_create"),
    path("items/<str:code>/", views.item_update, name="roadmap_item_update"),
    path("decisions/<str:code>/", views.decision_update, name="roadmap_decision_update"),
    path("checklist/<str:code>/", views.checklist_update, name="roadmap_checklist_update"),
]

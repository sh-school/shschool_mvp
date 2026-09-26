"""مسارا «مركز قيادة الجودة» — في المنصّة بجانب `roadmap/` (`shschool/urls.py`)، لمطوّرها وحدَه (`developer_only` في العرض).

أسماءٌ بفضاء `command_center` (`command_center:index` و`command_center:snapshot`). وكانت القشرةُ الأولى تحت `/admin/`
(QCC-01) خطأً في الإسناد: المالكُ طلبها في المنصّة، فنُقلت وحُذفت نسختُها (QCC-01b).
"""

from __future__ import annotations

from django.urls import path

from command_center import views

app_name = "command_center"

urlpatterns = [
    path("", views.index, name="index"),
    path("snapshot/", views.snapshot, name="snapshot"),
]

"""مساراتُ «عرض بصفة» تحت `/developer/view-as/` — W-20261009-032."""

from django.urls import path

from core.view_as import views

urlpatterns = [
    path("", views.picker, name="view_as_picker"),
    path("start/", views.start, name="view_as_start"),
    path("stop/", views.stop, name="view_as_stop"),
    path("linked/exit/", views.linked_exit, name="view_as_linked_exit"),
    path("linked/<uuid:pk>/", views.linked_switch, name="view_as_linked_switch"),
    path("linked/<uuid:pk>/confirm/", views.linked_confirm, name="view_as_linked_confirm"),
]

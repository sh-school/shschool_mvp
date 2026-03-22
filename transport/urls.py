from django.urls import path

from . import views

app_name = "transport"

urlpatterns = [
    path("", views.transport_dashboard, name="dashboard"),
    path("buses/", views.buses_list, name="buses_list"),
    path("bus/<uuid:bus_id>/", views.bus_detail, name="bus_detail"),
    path("bus/<uuid:bus_id>/route/new/", views.manage_route, name="create_route"),
    path("bus/<uuid:bus_id>/route/<uuid:route_id>/", views.manage_route, name="edit_route"),
    path("bus/<uuid:bus_id>/tracking/", views.tracking_map, name="tracking_map"),
    path("assignments/", views.student_assignments, name="student_assignments"),
    path("statistics/", views.transport_statistics, name="statistics"),
]

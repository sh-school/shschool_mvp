from django.urls import path
from . import views
app_name = 'breach'
urlpatterns = [
    path('',                        views.dashboard,     name='dashboard'),
    path('create/',                 views.create,        name='create'),
    path('<uuid:pk>/',              views.detail,        name='detail'),
    path('<uuid:pk>/status/',       views.update_status, name='update_status'),
    path('<uuid:pk>/pdf/',          views.breach_pdf,    name='pdf'),
]

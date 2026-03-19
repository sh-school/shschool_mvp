from django.urls import path
from core.views_auth import login_view, logout_view

urlpatterns = [
    path("login/",  login_view,  name="login"),
    path("logout/", logout_view, name="logout"),
]

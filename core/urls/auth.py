from django.urls import path
from core.views_auth import login_view, logout_view, force_change_password

urlpatterns = [
    path("login/",  login_view,  name="login"),
    path("logout/", logout_view, name="logout"),
    path("force_change_password/", force_change_password, name="force_change_password"),
]

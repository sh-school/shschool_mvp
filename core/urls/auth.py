from django.urls import path

from core.views_auth import (
    disable_2fa,
    force_change_password,
    login_view,
    logout_view,
    setup_2fa,
    verify_2fa,
)

urlpatterns = [
    path("login/", login_view, name="login"),
    path("logout/", logout_view, name="logout"),
    path("force_change_password/", force_change_password, name="force_change_password"),
    path("2fa/setup/", setup_2fa, name="setup_2fa"),
    path("2fa/verify/", verify_2fa, name="verify_2fa"),
    path("2fa/disable/", disable_2fa, name="disable_2fa"),
]

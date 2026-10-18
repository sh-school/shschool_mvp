from django.urls import path

from core.views_auth import (
    change_password,
    disable_2fa,
    force_change_password,
    login_view,
    logout_view,
    session_done,
    session_status,
    session_touch,
    setup_2fa,
    verify_2fa,
)

urlpatterns = [
    path("login/", login_view, name="login"),
    path("logout/", logout_view, name="logout"),
    path("session/status/", session_status, name="session_status"),
    path("session/touch/", session_touch, name="session_touch"),
    path("session/done/", session_done, name="session_done"),
    path("force_change_password/", force_change_password, name="force_change_password"),
    path("change-password/", change_password, name="change_password"),
    path("2fa/setup/", setup_2fa, name="setup_2fa"),
    path("2fa/verify/", verify_2fa, name="verify_2fa"),
    path("2fa/disable/", disable_2fa, name="disable_2fa"),
]

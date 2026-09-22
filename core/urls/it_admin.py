from django.urls import path

from core.views_it_admin import password_reset_action, password_reset_list

urlpatterns = [
    path("password-reset/", password_reset_list, name="it_admin_password_reset_list"),
    path(
        "password-reset/<uuid:user_id>/",
        password_reset_action,
        name="it_admin_password_reset_action",
    ),
]

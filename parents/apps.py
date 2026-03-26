from django.apps import AppConfig


class ParentsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "parents"
    verbose_name = "بوابة أولياء الأمور"

    def ready(self):
        from core.module_registry import register_module

        register_module(
            name="parents",
            label="بوابة أولياء الأمور",
            url_prefix="/parents/",
            icon="bi-people",
            allowed_roles={"parent", "principal", "vice_admin", "vice_academic", "admin"},
            sidebar_roles={"parent"},
            sort_order=70,
        )

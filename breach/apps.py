from django.apps import AppConfig


class BreachConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "breach"
    verbose_name = "خرق البيانات (PDPPL)"

    def ready(self):
        from core.module_registry import register_module

        register_module(
            name="breach",
            label="خرق البيانات",
            url_prefix="/breach/",
            icon="bi-shield-exclamation",
            allowed_roles={"principal", "vice_admin", "admin", "it_technician"},
            sort_order=90,
        )

from django.apps import AppConfig


class ClinicConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "clinic"
    verbose_name = "العيادة المدرسية"

    def ready(self):
        from core.module_registry import register_module

        register_module(
            name="clinic",
            label="العيادة الصحية",
            url_prefix="/clinic/",
            icon="bi-heart-pulse",
            allowed_roles={"principal", "vice_admin", "nurse"},
            sidebar_roles={"principal", "vice_admin", "nurse", "parent"},
            sort_order=50,
        )

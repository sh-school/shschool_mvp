from django.apps import AppConfig


class StagingConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "staging"
    verbose_name = "الاستيراد"

    def ready(self):
        from core.module_registry import register_module

        register_module(
            name="staging",
            label="الاستيراد والتصدير",
            url_prefix="/staging/",
            icon="bi-cloud-upload",
            allowed_roles={"principal", "vice_academic", "vice_admin", "admin", "secretary"},
            sort_order=85,
        )

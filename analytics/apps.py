from django.apps import AppConfig


class AnalyticsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "analytics"
    verbose_name = "الإحصاءات والتحليلات"

    def ready(self):
        from core.module_registry import register_module

        register_module(
            name="analytics",
            label="التحليلات والإحصاءات",
            url_prefix="/analytics/",
            icon="bi-graph-up",
            allowed_roles={
                "principal", "vice_academic", "vice_admin",
                "admin", "coordinator", "teacher", "ese_teacher",
                "social_worker", "psychologist", "academic_advisor",
                "nurse", "librarian",
            },
            sort_order=40,
        )

from django.apps import AppConfig


class ReportsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "reports"
    verbose_name = "التقارير والشهادات"

    def ready(self):
        from core.module_registry import register_module

        register_module(
            name="reports",
            label="التقارير والشهادات",
            url_prefix="/reports/",
            icon="bi-file-earmark-bar-graph",
            allowed_roles={
                "principal", "vice_academic", "vice_admin",
                "coordinator", "teacher", "ese_teacher",
            },
            sort_order=35,
        )

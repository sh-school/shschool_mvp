from django.apps import AppConfig


class ExamControlConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "exam_control"
    verbose_name = "كنترول الاختبارات"

    def ready(self):
        from core.module_registry import register_module

        register_module(
            name="exam_control",
            label="كنترول الاختبارات",
            url_prefix="/exam-control/",
            icon="bi-file-earmark-lock",
            allowed_roles={
                "principal", "vice_academic", "vice_admin",
                "coordinator", "admin_supervisor", "admin",
            },
            sort_order=15,
        )

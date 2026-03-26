from django.apps import AppConfig


class AssessmentsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "assessments"
    verbose_name = "التقييمات والاختبارات"

    def ready(self):
        from core.module_registry import register_module

        register_module(
            name="assessments",
            label="التقييمات والدرجات",
            url_prefix="/assessments/",
            icon="bi-journal-check",
            allowed_roles={
                "principal", "vice_academic", "vice_admin",
                "coordinator", "teacher", "ese_teacher",
                "admin", "academic_advisor",
            },
            sidebar_roles={
                "principal", "vice_academic", "vice_admin",
                "coordinator", "teacher", "ese_teacher",
                "admin", "academic_advisor",
                "parent", "student",
            },
            sort_order=10,
        )

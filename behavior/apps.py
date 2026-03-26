from django.apps import AppConfig


class BehaviorConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "behavior"
    verbose_name = "الانضباط السلوكي والتحفيز التربوي"

    def ready(self):
        from core.module_registry import register_module

        register_module(
            name="behavior",
            label="السلوك والانضباط",
            url_prefix="/behavior/",
            icon="bi-shield-check",
            allowed_roles={
                "principal", "vice_admin", "vice_academic",
                "coordinator", "teacher", "ese_teacher",
                "specialist", "social_worker", "psychologist",
                "admin_supervisor",
            },
            sidebar_roles={
                "principal", "vice_admin", "vice_academic",
                "coordinator", "teacher", "ese_teacher",
                "specialist", "social_worker", "psychologist",
                "admin_supervisor",
                "parent", "student",
            },
            sort_order=30,
        )

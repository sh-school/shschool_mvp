from django.apps import AppConfig


class OperationsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "operations"
    verbose_name = "العمليات"

    def ready(self):
        from core.module_registry import register_module

        register_module(
            name="schedule",
            label="الجدول الدراسي",
            url_prefix="/operations/schedule/",
            icon="bi-calendar-week",
            allowed_roles={
                "principal", "vice_academic", "vice_admin",
                "coordinator", "teacher", "ese_teacher",
                "academic_advisor", "admin_supervisor",
                "student", "parent",
                # v7 — لديهم حصص في الجدول
                "activities_coordinator", "teacher_assistant", "ese_assistant",
                "speech_therapist", "occupational_therapist",
                "receptionist",
            },
            sort_order=5,
        )
        register_module(
            name="attendance",
            label="الحضور والغياب",
            url_prefix="/operations/",
            icon="bi-person-check",
            allowed_roles={
                "principal", "vice_academic", "vice_admin",
                "coordinator", "teacher", "ese_teacher",
                "academic_advisor", "admin_supervisor",
                "parent", "student",
                # v7
                "activities_coordinator", "teacher_assistant", "ese_assistant",
                "speech_therapist", "occupational_therapist",
                "receptionist",
            },
            sort_order=6,
        )

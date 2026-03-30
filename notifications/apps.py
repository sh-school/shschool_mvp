from django.apps import AppConfig


class NotificationsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "notifications"
    verbose_name = "الإشعارات"

    def ready(self):
        from core.module_registry import register_module

        register_module(
            name="notifications",
            label="الإشعارات",
            url_prefix="/notifications/",
            icon="bi-bell",
            allowed_roles={
                "principal", "vice_academic", "vice_admin",
                "coordinator", "teacher", "ese_teacher",
                "specialist", "social_worker", "psychologist",
                "academic_advisor", "admin_supervisor",
                "nurse", "librarian", "bus_supervisor",
                "admin", "secretary", "it_technician",
                # v7
                "activities_coordinator", "teacher_assistant", "ese_assistant",
                "speech_therapist", "occupational_therapist",
                "receptionist", "transport_officer",
            },
            sort_order=80,
        )

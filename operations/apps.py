from django.apps import AppConfig


class OperationsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "operations"
    verbose_name = "العمليات"

    def ready(self):
        import operations.signals  # noqa: F401
        from core.exports import registry as export_registry
        from core.module_registry import register_module

        from . import schedule_export_builders as builders

        # تصديرُ الجدول عبر السجلّ المركزيّ (VI-30ب): خلفيٌّ كلُّه — الأثقلُ 19.9ث، وPDF الجدول العامّ أبطأُ من ثانية.
        export_registry.register(
            "schedule.pdf", build=builders.build_schedule_pdf, capability="schedule.print"
        )
        export_registry.register(
            "schedule.xlsx", build=builders.build_schedule_xlsx, capability="schedule.print"
        )
        export_registry.register(
            "schedule.pages_pdf",
            build=builders.build_schedule_pages_pdf,
            capability="schedule.browse",
        )

        register_module(
            name="schedule",
            label="الجدول الدراسي",
            url_prefix="/operations/schedule/",
            allowed_roles={
                "principal",
                "vice_academic",
                "vice_admin",
                "coordinator",
                "teacher",
                "ese_teacher",
                "academic_advisor",
                "admin_supervisor",
                "student",
                "parent",
                # v7 — لديهم حصص في الجدول
                "activities_coordinator",
                "e_projects_coordinator",
                "teacher_assistant",
                "ese_assistant",
                "speech_therapist",
                "occupational_therapist",
                "receptionist",
            },
            sort_order=5,
        )
        register_module(
            name="attendance",
            label="الحضور والغياب",
            url_prefix="/operations/",
            allowed_roles={
                "principal",
                "vice_academic",
                "vice_admin",
                "coordinator",
                "teacher",
                "ese_teacher",
                "academic_advisor",
                "admin_supervisor",
                "parent",
                "student",
                # v7
                "activities_coordinator",
                "e_projects_coordinator",
                "teacher_assistant",
                "ese_assistant",
                "speech_therapist",
                "occupational_therapist",
                "receptionist",
            },
            sort_order=6,
        )

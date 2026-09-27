from django.apps import AppConfig


class ReportsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "reports"
    verbose_name = "التقارير والشهادات"

    def ready(self):
        from core.exports import registry as export_registry
        from core.module_registry import register_module

        from . import export_builders as builders

        # شهاداتُ الفصل PDF عبر السجلّ المركزيّ (VI-30ب): خلفيٌّ — 2.9ث متزامناً. المعاينةُ والإطارُ المضمَّنُ في العارض يبقيان في الـview.
        export_registry.register(
            "reports.class_certificates",
            build=builders.build_class_certificates_pdf,
            capability="reports.school",
        )

        register_module(
            name="reports",
            label="التقارير والشهادات",
            url_prefix="/reports/",
            allowed_roles={
                "principal",
                "vice_academic",
                "vice_admin",
                "coordinator",
                "teacher",
                "ese_teacher",
                # v7
                "activities_coordinator",
                "e_projects_coordinator",
                "teacher_assistant",
                "ese_assistant",
                "speech_therapist",
                "occupational_therapist",
            },
            sort_order=35,
        )

from django.apps import AppConfig


class ReportsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "reports"
    verbose_name = "التقارير والشهادات"

    def ready(self):
        from core.exports import registry as export_registry
        from core.module_registry import register_module

        from . import export_builders as builders
        from .export_tables import register_report_tables

        # شهاداتُ الفصل PDF عبر السجلّ المركزيّ (VI-30ب): خلفيٌّ — 2.9ث متزامناً. المعاينةُ والإطارُ المضمَّنُ في العارض يبقيان في الـview.
        export_registry.register(
            "reports.class_certificates",
            build=builders.build_class_certificates_pdf,
            capability="reports.school",
        )

        # كشفُ نتائج الفصل Excel على عقد الجداول (W-20261109-007): خلفيٌّ، والزرُّ يمرّ على مركز التصدير (`data-app-file`).
        register_report_tables()

        # كشفا الغياب والمخالفات Excel: خلفيّان (W-20261021-011) — بلا قياس p95 يثبت أنّهما سريعان فالافتراضُ job.
        export_registry.register(
            "reports.attendance_xlsx",
            build=builders.build_attendance_xlsx,
            capability="reports.school",
        )
        export_registry.register(
            "reports.behavior_xlsx",
            build=builders.build_behavior_xlsx,
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
                "student_affairs_coordinator",
            },
            sort_order=35,
        )

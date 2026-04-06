from django.apps import AppConfig


class QualityConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "quality"
    verbose_name = "الجودة والخطة التشغيلية"

    def ready(self):
        from core.module_registry import register_module

        # الوحدة الفرعية أولاً (أطول مسار)
        register_module(
            name="quality_evaluations",
            label="تقييمات الجودة",
            url_prefix="/quality/evaluations/",
            icon="bi-clipboard-check",
            allowed_roles={
                "principal",
                "vice_admin",
                "vice_academic",
                "coordinator",
                "teacher",
                "ese_teacher",
                "specialist",
                "social_worker",
                "psychologist",
                "academic_advisor",
                "nurse",
                "librarian",
                "bus_supervisor",
                "admin_supervisor",
                "admin",
                "secretary",
                "it_technician",
                # v7 — كل الموظفين يُقيَّمون
                "activities_coordinator",
                "teacher_assistant",
                "ese_assistant",
                "speech_therapist",
                "occupational_therapist",
                "receptionist",
                "transport_officer",
            },
            sort_order=21,
            parent="quality",
        )
        register_module(
            name="quality",
            label="الجودة والتطوير",
            url_prefix="/quality/",
            icon="bi-award",
            allowed_roles={
                "principal",
                "vice_admin",
                "vice_academic",
                "coordinator",
                "teacher",
                "ese_teacher",
                "specialist",
                "social_worker",
                "psychologist",
            },
            sort_order=20,
        )

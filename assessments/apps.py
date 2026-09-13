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
                "principal",
                "vice_academic",
                "vice_admin",
                "coordinator",
                "teacher",
                "ese_teacher",
                "admin",
                "academic_advisor",
                # v7 — مساعدون يدعمون إدخال الدرجات
                "teacher_assistant",
                # الوراثةُ تُدخلهم في حارس الواجهة، فتسعهم بوّابةُ المسار (اختبار `test_module_gates_match_guards`)
                "activities_coordinator",
                "e_projects_coordinator",
                "ese_assistant",
            },
            sidebar_roles={
                "principal",
                "vice_academic",
                "vice_admin",
                "coordinator",
                "teacher",
                "ese_teacher",
                "admin",
                "academic_advisor",
            },
            sort_order=10,
        )

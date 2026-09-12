from django.apps import AppConfig


class LibraryConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "library"
    verbose_name = "المكتبة ومصادر التعلم"

    def ready(self):
        from core.module_registry import register_module

        register_module(
            name="library",
            label="المكتبة",
            url_prefix="/library/",
            icon="bi-book",
            allowed_roles={
                "principal",
                "vice_admin",
                "librarian",
                "teacher",
                "coordinator",
                "ese_teacher",
                "specialist",
                "social_worker",
                "student",
                # v7 — مساعدون + منسق أنشطة يستعيرون كتباً
                "activities_coordinator",
                "e_projects_coordinator",
                "teacher_assistant",
                # الوراثةُ تُدخلهم في حارس الواجهة، فتسعهم بوّابةُ المسار (اختبار `test_module_gates_match_guards`)
                "vice_academic",
                "ese_assistant",
            },
            sort_order=55,
        )

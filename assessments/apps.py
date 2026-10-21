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
                # قرارُ عذر الغياب عن الاختبار (D-402م): بوّابةُ المسار تسعهم، وحارسُ كلّ عرضٍ بقدرته
                # يحجب عنهم ما سوى `excuse_queue` و`decide_excuse` (اختبارُ ذلك في test_exam_excuse_decision).
                "student_affairs_coordinator",
                "admin_supervisor",
                "social_worker",
                "psychologist",
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

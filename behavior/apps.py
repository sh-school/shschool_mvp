from django.apps import AppConfig


class BehaviorConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "behavior"
    verbose_name = "الانضباط السلوكي والتحفيز التربوي"

    def ready(self):
        from core.module_registry import register_module
        from reports import export_builders  # noqa: F401 — استيرادُه يسجّل PDF الإحصاء

        from .export_tables import register_behavior_tables

        # التقرير اليوميّ والإحصاءاتُ وملفُّ الطالب على عقد الجداول: خلفيّةٌ (الافتراضيُّ الآمن)، بنطاق صاحب الطلب.
        register_behavior_tables()

        register_module(
            name="behavior",
            label="السلوك والانضباط",
            url_prefix="/behavior/",
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
                "admin_supervisor",
                # بوابةٌ فقط: تسجيلُ المخالفة من قائمة إدارة شؤون الطلاب (D-273م)، وكلُّ شاشةٍ تقرّر بحارسها.
                "student_affairs_coordinator",
                # v7 — مساعدون + منسق أنشطة يبلّغون عن مخالفات
                "activities_coordinator",
                "e_projects_coordinator",
                "teacher_assistant",
                "ese_assistant",
            },
            sidebar_roles={
                "principal",
                "vice_admin",
                "vice_academic",
                "coordinator",
                "teacher",
                "ese_teacher",
                "specialist",
                "social_worker",
                "psychologist",
                "admin_supervisor",
                "student_affairs_coordinator",  # قرارُ المالك 2026-10-18 (W-20261018-003)
            },
            sort_order=30,
        )

from django.apps import AppConfig


class StudentAffairsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "student_affairs"
    verbose_name = "شؤون الطلاب"

    def ready(self):
        from core.exports import registry as export_registry

        from . import export_builders as builders

        # قائمةُ الطلاب PDF عبر السجلّ المركزيّ (VI-30ب): خلفيٌّ — 8.3ث متزامناً. Excel (0.8ث) ينتظر قياسَ p95 دافئاً.
        export_registry.register(
            "student_affairs.students_pdf",
            build=builders.build_students_pdf,
            capability="student_affairs.manage",
        )

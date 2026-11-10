from django.apps import AppConfig


class StudentAffairsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "student_affairs"
    verbose_name = "شؤون الطلاب"

    def ready(self):
        from core.exports import contract
        from core.exports import registry as export_registry

        from . import export_builders as builders
        from .followup_tables import register_followup_tables

        # قائمةُ الطلاب PDF عبر السجلّ المركزيّ (VI-30ب): خلفيٌّ — 8.3ث متزامناً. Excel (0.8ث) ينتظر قياسَ p95 دافئاً.
        export_registry.register(
            "student_affairs.students_pdf",
            build=builders.build_students_pdf,
            capability="student_affairs.manage",
        )
        # قائمةُ الطلبة Excel على عقد التصدير المركزيّ: المعروضُ بعد الفلترة وبنطاق الدور (W-20261109-013).
        contract.register_table(builders.STUDENT_LIST_TABLE)
        # الحضورُ والسلوكُ والتأخّرُ والأنشطةُ والتحرّكاتُ على العقد نفسِه — Excel وPDF بمحدِّد الصفحة (W-20261109-006).
        register_followup_tables()

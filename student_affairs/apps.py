from django.apps import AppConfig


class StudentAffairsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "student_affairs"
    verbose_name = "شؤون الطلاب"

    def ready(self):
        from core.exports import registry as export_registry

        from . import export_builders as builders
        from . import export_tables

        # قائمةُ الطلاب PDF عبر السجلّ المركزيّ (VI-30ب): خلفيٌّ — 8.3ث متزامناً. Excel (0.8ث) ينتظر قياسَ p95 دافئاً.
        export_registry.register(
            "student_affairs.students_pdf",
            build=builders.build_students_pdf,
            capability="student_affairs.manage",
        )
        # تحرّكات الطلبة Excel: خلفيٌّ افتراضاً — لا قياسَ p95 مثبَّتاً بعد.
        export_registry.register(
            "student_affairs.movements_xlsx",
            build=builders.build_movements_xlsx,
            capability="student_affairs.transfers",
        )
        # النوعُ التجريبيُّ لعقد التصدير الجدوليّ (W-20261109-001): كشفُ الطلاب بنطاق الدور — Excel وPDF.
        from core.exports.table import register_table

        register_table(export_tables.ROSTER, capability="student_affairs.view")

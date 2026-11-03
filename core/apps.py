from django.apps import AppConfig


class CoreConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "core"
    verbose_name = "النواة"

    def ready(self) -> None:
        import core.signals  # noqa
        from django.db.models.signals import post_migrate

        from core.admin_axes import install
        from core.admin_hidden import hide_unused_jwt_tables
        from core.permission_names import arabize_permission_names

        install()
        hide_unused_jwt_tables()
        self._register_exports()
        # بعد `create_permissions` (مسجَّلٌ قبلنا: auth قبل core في INSTALLED_APPS) لكلّ تطبيق — راجع الوحدة.
        post_migrate.connect(
            arabize_permission_names, dispatch_uid="core.permission_names.arabize_permission_names"
        )

    @staticmethod
    def _register_exports() -> None:
        from core.exports import registry as export_registry

        from . import student_export_builder as builders

        # كشفُ الطلاب الكامل Excel: خلفيٌّ (W-20261021-011) — بلا قياس p95 يثبت أنّه سريع فالافتراضُ job.
        export_registry.register(
            "core.students_xlsx",
            build=builders.build_students_xlsx,
            capability="students.import_export",
        )

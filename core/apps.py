from django.apps import AppConfig


class CoreConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "core"
    verbose_name = "النواة"

    def ready(self):
        import core.signals  # noqa
        from django.db.models.signals import post_migrate

        from core.admin_axes import install
        from core.admin_hidden import hide_unused_jwt_tables
        from core.permission_names import arabize_permission_names

        install()
        hide_unused_jwt_tables()
        # بعد `create_permissions` (مسجَّلٌ قبلنا: auth قبل core في INSTALLED_APPS) لكلّ تطبيق — راجع الوحدة.
        post_migrate.connect(
            arabize_permission_names, dispatch_uid="core.permission_names.arabize_permission_names"
        )

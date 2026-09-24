from django.apps import AppConfig


class CoreConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "core"
    verbose_name = "النواة"

    def ready(self):
        import core.signals  # noqa
        from core.admin_axes import install
        from core.admin_hidden import hide_unused_jwt_tables

        install()
        hide_unused_jwt_tables()

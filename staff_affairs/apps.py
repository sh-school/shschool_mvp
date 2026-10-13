from django.apps import AppConfig


class StaffAffairsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "staff_affairs"
    verbose_name = "شؤون الموظفين"

    def ready(self) -> None:
        # لوحةُ السكرتير بياناتُها هنا، فتسجّلها الوحدةُ لتقرأها النواةُ بلا استيرادٍ نازل.
        from core.dashboard_registry import register_role_dashboard

        from .dashboard import secretary_context

        register_role_dashboard("secretary", secretary_context)

        # قراءةُ التكليف تسجّلها النواةُ كمصدرٍ لا استيراداً نازلاً (W-20261001-021).
        from core.capabilities import register_acting_roles_provider

        from .attendance.assignments import acting_roles

        register_acting_roles_provider(acting_roles)

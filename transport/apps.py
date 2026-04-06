from django.apps import AppConfig


class TransportConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "transport"
    verbose_name = "النقل والمواصلات"

    def ready(self):
        from core.module_registry import register_module

        register_module(
            name="transport",
            label="النقل المدرسي",
            url_prefix="/transport/",
            icon="bi-bus-front",
            allowed_roles={"principal", "vice_admin", "bus_supervisor", "transport_officer"},
            sidebar_roles={
                "principal",
                "vice_admin",
                "bus_supervisor",
                "transport_officer",
                "parent",
            },
            sort_order=60,
        )

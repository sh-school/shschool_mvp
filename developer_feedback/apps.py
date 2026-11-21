from django.apps import AppConfig


class DeveloperFeedbackConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "developer_feedback"
    verbose_name = "ملاحظات المطوّر (أرسل إلى المطوّر)"

    def ready(self) -> None:
        # تسجيل فحص Django الذي يحذّر عند غياب المستلِم في الإنتاج
        from developer_feedback import checks  # noqa: F401

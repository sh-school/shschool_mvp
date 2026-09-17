from django.apps import AppConfig


class ParentsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "parents"
    verbose_name = "بوابة أولياء الأمور"

    def ready(self):
        from core.module_registry import register_module
        from core.parent_consent import holds_parent_membership

        register_module(
            name="parents",
            label="بوابة أولياء الأمور",
            url_prefix="/parents/",
            icon="bi-people",
            allowed_roles={"parent", "principal", "vice_admin", "vice_academic", "admin"},
            sidebar_roles={"parent"},
            # الكادرُ الذي هو وليُّ أمرٍ أيضاً يدخل بوّابتَه بعضويّته تلك لا بدوره
            # الحاكم (قرارُ 2026-09-16) — ويرى أبناءه وحدَهم، وحرّاسُ الشاشات باقون.
            grant=holds_parent_membership,
            sort_order=70,
        )

from django.apps import AppConfig


class BreachConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "breach"
    verbose_name = "خرق البيانات (PDPPL)"

    def ready(self):
        from core.module_registry import register_module

        register_module(
            name="breach",
            label="خرق البيانات",
            url_prefix="/breach/",
            icon="bi-shield-exclamation",
            # والنائبُ الأكاديميُّ يرث المنسّقَ فالمعلّم، فيمرّ من حارس الواجهة —
            # وكانت البوّابةُ تردّه (اختبار `test_module_gates_match_guards`).
            allowed_roles={
                "principal",
                "vice_admin",
                "vice_academic",
                "admin",
                "it_technician",
            },
            sort_order=90,
        )

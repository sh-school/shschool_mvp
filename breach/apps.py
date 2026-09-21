from django.apps import AppConfig


class BreachConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "breach"
    verbose_name = "خرق البيانات (PDPPL)"

    def ready(self):
        from core.capabilities import capability
        from core.module_registry import register_module

        register_module(
            name="breach",
            label="خرق البيانات",
            url_prefix="/breach/",
            # والنائبُ الأكاديميُّ يرث المنسّقَ فالمعلّم، فيمرّ من حارس الواجهة —
            # وكانت البوّابةُ تردّه (اختبار `test_module_gates_match_guards`).
            # مصدرٌ واحد: القدرةُ هي المرجع. كانت القائمتان تنجرفان فيُردّ من تسمح له
            # القدرةُ قبل أن تُقرأ (مطوّرُ المنصّة، `it_technician`).
            allowed_roles=set(capability("breach.manage").expanded_roles),
            sort_order=90,
        )

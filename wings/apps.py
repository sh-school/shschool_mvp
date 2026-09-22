from django.apps import AppConfig


class WingsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "wings"
    verbose_name = "أجنحة المدرسة"

    def ready(self):
        from core.models.academic import WingCoverage
        from core.module_registry import register_module

        # النطاقُ مفتوحٌ على الأجنحة الخمسة حتّى تُبنى المرحلة 3 (`wing_scoped`):
        # المشرفُ اليومَ يرى كلَّ طلاب المدرسة أصلاً، فقصرُ هذه الشاشة وحدَها
        # على جناحه يوهم بقيدٍ لا وجودَ له في بقيّة المنصّة.
        register_module(
            name="wings",
            label="أجنحة المدرسة",
            url_prefix="/wings/",
            # وأدوارُ البديل (قرارُ المدير: مشرفٌ إداريٌّ أو ملاحظُ طلبةٍ أو عاملُ خدمات):
            # البوّابةُ تُدخلهم، وكلُّ شاشةٍ تقرّر بحارسها — والرصدُ يُفتح لمن يحمل الجناحَ
            # بتكليفه (`wings.record_day`)، والطوابقُ والتكليفُ لا.
            allowed_roles={
                "principal",
                "vice_admin",
                "vice_academic",
                "admin_supervisor",
                "platform_developer",
                *WingCoverage.SUBSTITUTE_ROLES,
            },
            sidebar_roles={
                "principal",
                "vice_admin",
                "vice_academic",
                "admin_supervisor",
                "platform_developer",
            },
            sort_order=22,
        )

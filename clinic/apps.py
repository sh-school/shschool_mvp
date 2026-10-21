from django.apps import AppConfig


class ClinicConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "clinic"
    verbose_name = "العيادة المدرسية"

    def ready(self):
        from core.exports import registry as export_registry
        from core.module_registry import register_module

        from .export import build_monthly_export, build_monthly_pdf

        # التقريرُ الشهريّ Excel (W-20261020-032): عدديٌّ بلا أسماء، بقدرةٍ مستقلّةٍ عن قراءة الوحدة.
        export_registry.register(
            "clinic.monthly_xlsx", build=build_monthly_export, capability="clinic.export"
        )
        export_registry.register(
            "clinic.monthly_pdf", build=build_monthly_pdf, capability="clinic.export"
        )

        register_module(
            name="clinic",
            label="العيادة الصحية",
            url_prefix="/clinic/",
            allowed_roles={"principal", "vice_admin", "nurse", "student_affairs_coordinator"},
            # ووليُّ الأمر والطالبُ ليسا هنا: بابُهما `/parents/`، وواجهاتُ هذه
            # الوحدة كلُّها للكادر. ووعدٌ في القائمة تردُّه البوّابةُ رابطٌ يُفضي
            # إلى ٤٠٣ (اختبار `test_module_gates_match_guards`).
            sidebar_roles={"principal", "vice_admin", "nurse", "student_affairs_coordinator"},
            sort_order=50,
        )

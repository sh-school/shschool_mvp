from django.apps import AppConfig


class ClinicConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "clinic"
    verbose_name = "العيادة المدرسية"

    def ready(self):
        from core.module_registry import register_module

        register_module(
            name="clinic",
            label="العيادة الصحية",
            url_prefix="/clinic/",
            icon="bi-heart-pulse",
            allowed_roles={"principal", "vice_admin", "nurse"},
            # ووليُّ الأمر والطالبُ ليسا هنا: بابُهما `/parents/`، وواجهاتُ هذه
            # الوحدة كلُّها للكادر. ووعدٌ في القائمة تردُّه البوّابةُ رابطٌ يُفضي
            # إلى ٤٠٣ (اختبار `test_module_gates_match_guards`).
            sidebar_roles={"principal", "vice_admin", "nurse"},
            sort_order=50,
        )

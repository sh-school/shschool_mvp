from django.apps import AppConfig


class AcademicManagementConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "academic_management"
    verbose_name = "إدارة الشؤون الأكاديمية"

    def ready(self):
        from .export_tables import register_academic_tables

        # التقاريرُ الأربعةُ على عقد الجداول: خلفيّةٌ (الافتراضيُّ الآمن)، المحدِّدُ نفسُه للصفحة والملفّ.
        register_academic_tables()

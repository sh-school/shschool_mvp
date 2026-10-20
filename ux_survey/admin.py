"""لوحة Django: الموجاتُ تُدار، والإجاباتُ والمشاركاتُ للقراءة فقط، والنصوصُ الحرّة لا تُعرض هنا أبدًا."""

from django.contrib import admin

from ux_survey.models import SurveyParticipation, SurveyResponse, SurveyWave


@admin.register(SurveyWave)
class SurveyWaveAdmin(admin.ModelAdmin):
    list_display = ("name", "is_active", "snooze_days")
    list_filter = ("is_active",)


class _ReadOnly(admin.ModelAdmin):
    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(SurveyResponse)
class SurveyResponseAdmin(_ReadOnly):
    """بلا `hardest_task` و`wish`: المراجعةُ البشريّة في شاشة المراجعة للمطوّر المالك."""

    list_display = ("wave", "role_group", "week", "review")
    list_filter = ("wave", "role_group", "review")
    exclude = ("hardest_task", "wish")


@admin.register(SurveyParticipation)
class SurveyParticipationAdmin(_ReadOnly):
    """من تعامل مع الاستبانة وحالتُه — لا شيءَ من الإجابة."""

    list_display = ("user", "wave", "status", "snooze_until")
    list_filter = ("wave", "status")

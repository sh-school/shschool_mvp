"""لوحةُ إدارةِ حَوكمة الأنصبة — تهيئةٌ نادرةٌ لا شاشةَ لها.

`WorkloadGovernance` تحمل قراراتٍ تُتَّخذ مرّةً في العام أو أقلّ: من يُدخل ومن
يراجع ومن يعتمد، وأيجوز أن يعتمدها من راجعها، والنصابُ المرجعيّ. فلا تستحقّ
شاشةً في المنصّة، لكنّها لا تستحقّ أن تكون خارجَ المتناول أيضاً.

وقد كانت كذلك: `allow_self_approval` مكتوبٌ في النموذج ويقرؤه حارسُ الاعتماد،
والرسالةُ تقول «وإن أرادت المدرسةُ الجمعَ فبتهيئةٍ صريحةٍ تُسجَّل» — والتهيئةُ
لا يبلغها أحد. مخرجٌ موعودٌ لا بابَ له.
"""

from django.contrib import admin

from academic_management.models import WorkloadGovernance


@admin.register(WorkloadGovernance)
class WorkloadGovernanceAdmin(admin.ModelAdmin):
    list_display = ("school", "allow_self_approval", "reference_load")
    list_filter = ("allow_self_approval",)
    search_fields = ("school__name", "school__code")
    fieldsets = (
        (None, {"fields": ("school",)}),
        (
            "من يفعل ماذا",
            {
                "fields": ("edit_roles", "review_roles", "approve_roles"),
                "description": (
                    "قوائمُ أدوارٍ بأسمائها البرمجيّة. والفراغُ يعني الافتراضَ الموصى به، "
                    "ومطوّرُ المنصّة مضافٌ في كلّ حالٍ فلا تُقصيه تهيئة."
                ),
            },
        ),
        (
            "فصلُ المهام",
            {
                "fields": ("allow_self_approval",),
                "description": (
                    "الأصلُ أن يفصل: من راجع الخطّة لا يعتمدها، وإلّا فُقدت المراجعةُ "
                    "المستقلّة. وتفعيلُ هذا الخيار تجاوزٌ مقصودٌ يُسجَّل في سجلّ التدقيق "
                    "عند كلّ اعتمادٍ يستعمله — لا سلوكٌ صامت."
                ),
            },
        ),
        ("النصاب المرجعيّ", {"fields": ("reference_load",)}),
    )

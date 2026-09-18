from decimal import Decimal
from typing import Any

from django import forms
from django.contrib import admin, messages
from django.core.exceptions import PermissionDenied

from .models import (
    AnnualSubjectResult,
    Assessment,
    AssessmentPackage,
    ExamDeprivation,
    ExamMisconduct,
    StudentAssessmentGrade,
    StudentSubjectResult,
    SubjectClassSetup,
)


@admin.register(SubjectClassSetup)
class SubjectClassSetupAdmin(admin.ModelAdmin):
    list_display = (
        "subject",
        "class_group",
        "teacher",
        "academic_year",
        "is_active",
        "has_pass_mark",
    )
    list_filter = ("school", "academic_year", "is_active")
    list_select_related = ("subject", "class_group", "teacher", "school")
    search_fields = ("subject__name_ar", "teacher__full_name", "class_group__section")
    autocomplete_fields = ("subject", "class_group", "teacher")


class AssessmentInline(admin.TabularInline):
    model = Assessment
    extra = 0
    fields = ("title", "assessment_type", "date", "max_grade", "weight_in_package", "status")


@admin.register(AssessmentPackage)
class AssessmentPackageAdmin(admin.ModelAdmin):
    list_display = (
        "get_subject",
        "get_class",
        "package_type",
        "semester",
        "weight",
        "semester_max_grade",
        "effective_max_grade",
        "is_active",
    )
    list_filter = ("package_type", "semester", "school", "is_active")
    list_select_related = ("setup__subject", "setup__class_group", "school")
    search_fields = ("setup__subject__name_ar",)
    autocomplete_fields = ("setup",)
    inlines = [AssessmentInline]

    def get_subject(self, obj):
        return obj.setup.subject.name_ar

    def get_class(self, obj):
        return str(obj.setup.class_group)

    get_subject.short_description = "المادة"
    get_class.short_description = "الفصل"


@admin.register(Assessment)
class AssessmentAdmin(admin.ModelAdmin):
    list_display = (
        "title",
        "get_subject",
        "get_class",
        "assessment_type",
        "get_semester",
        "date",
        "status",
        "max_grade",
    )
    list_filter = ("assessment_type", "status", "school", "package__semester")
    list_select_related = ("package__setup__subject", "package__setup__class_group", "school")
    search_fields = ("title", "package__setup__subject__name_ar")
    autocomplete_fields = ("package", "created_by")

    def get_subject(self, obj):
        return obj.subject.name_ar

    def get_class(self, obj):
        return str(obj.class_group)

    def get_semester(self, obj):
        return obj.package.get_semester_display()

    get_subject.short_description = "المادة"
    get_class.short_description = "الفصل"
    get_semester.short_description = "الفصل الدراسي"


@admin.register(StudentAssessmentGrade)
class StudentAssessmentGradeAdmin(admin.ModelAdmin):
    list_display = ("student", "assessment", "grade", "is_absent", "is_excused", "entered_at")
    list_filter = ("is_absent", "school", "assessment__package__semester")
    list_select_related = ("student", "assessment__package__setup__subject", "school")
    search_fields = ("student__full_name", "student__national_id", "assessment__title")
    autocomplete_fields = ("student", "assessment", "entered_by")


@admin.register(StudentSubjectResult)
class StudentSubjectResultAdmin(admin.ModelAdmin):
    list_display = (
        "student",
        "get_subject",
        "get_class",
        "semester",
        "p1_score",
        "p2_score",
        "p3_score",
        "p4_score",
        "p_aw_score",
        "total",
        "semester_max",
    )
    list_filter = ("semester", "school")
    list_select_related = ("student", "setup__subject", "setup__class_group", "school")
    search_fields = ("student__full_name", "student__national_id")
    autocomplete_fields = ("student", "setup")

    def get_subject(self, obj):
        return obj.setup.subject.name_ar

    def get_class(self, obj):
        return str(obj.setup.class_group)

    get_subject.short_description = "المادة"
    get_class.short_description = "الفصل"


class AnnualSubjectResultForm(forms.ModelForm):
    """رصدُ الدور الثاني وحدَه — والحكمُ يُقرأ ولا يُحرَّر (يُعاد حسابُه من `judge_student`).

    الدرجةُ لا تتجاوز قصوى اختبار المادّة المخزَّنةَ مع الحكم (`second_round_max`): المعذورُ
    عن نهاية الفصل الثاني وحدَها يُختبر في منهاجها من 40 (م25 ص22)، وغيرُه من مئة (م14).
    """

    class Meta:
        model = AnnualSubjectResult
        fields = ("second_round_score", "second_round_absent")

    def clean(self) -> dict[str, Any]:
        data: dict[str, Any] = super().clean() or {}
        score = data.get("second_round_score")
        limit = self.instance.second_round_max or Decimal("100")
        if score is not None and score > limit:
            self.add_error(
                "second_round_score",
                f"قصوى اختبار الدور الثاني في هذه المادّة {limit} "
                f"({self.instance.article or 'م14'}) — لا {score}.",
            )
        if score is not None and data.get("second_round_absent"):
            self.add_error("second_round_absent", "درجةٌ مرصودة وغيابٌ معاً.")
        return data


@admin.register(AnnualSubjectResult)
class AnnualSubjectResultAdmin(admin.ModelAdmin):
    form = AnnualSubjectResultForm
    fields = (
        "student",
        "setup",
        "academic_year",
        "s1_total",
        "s2_total",
        "annual_total",
        "status",
        "standing",
        "mark",
        "article",
        "review",
        "second_round_max",
        "second_round_score",
        "second_round_absent",
    )
    readonly_fields = fields[:12]
    list_display = (
        "student",
        "get_subject",
        "get_class",
        "academic_year",
        "s1_total",
        "s2_total",
        "annual_total",
        "status",
        "standing",
        "article",
        "second_round_max",
        "second_round_score",
        "letter_grade",
    )
    list_filter = ("status", "standing", "school", "academic_year")
    list_select_related = ("student", "setup__subject", "setup__class_group", "school")
    search_fields = ("student__full_name", "student__national_id")

    def has_add_permission(self, request):
        # النتيجةُ يكتبها الحكمُ (`GradeService.recalculate_students`) لا اليد.
        return False

    def save_model(self, request, obj, form, change):
        """الرصدُ ثمّ الحكم: يُعاد الحكمُ على الطالب في موادّه (مسجَّلاً بفاعله) — للعام الجاري."""
        from .services import GradeService, is_open_year

        if not is_open_year(obj.setup):
            raise PermissionDenied("العامُ الدراسيّ مغلق — لا يُرصد فيه دورٌ ثانٍ.")
        # نتائجُ الشعبة إن كانت بقواعد أقدم ستُعاد كتابتُها كلُّها مع هذا الرصد — يُعرف قبله
        # فيُخبَر المستخدمُ بعده، لا أن يبقى صامتاً. (جولة 9.)
        will_restamp = GradeService.is_deferred(obj.setup.class_group, obj.setup.academic_year)
        GradeService.record_second_round(obj, request.user)
        # `hasattr` لأنّ `save_model` يُستدعى أحياناً بطلبٍ خامٍ بلا وسيط الرسائل (اختباراتٌ
        # تستدعيه مباشرةً) — فلا يُسقط استدعاءٌ لا يعرض شيئاً للمستخدم أصلاً.
        if will_restamp and hasattr(request, "_messages"):
            self.message_user(
                request,
                "نتائجُ شعبة هذا الطالب كانت بقواعد حكمٍ أقدم — أُعيد حسابُها كلُّها الآن.",
                level="warning",
            )

    def get_subject(self, obj):
        return obj.setup.subject.name_ar

    def get_class(self, obj):
        return str(obj.setup.class_group)

    def letter_grade(self, obj):
        return obj.letter_grade

    get_subject.short_description = "المادة"
    get_class.short_description = "الفصل"
    letter_grade.short_description = "التقدير"


class _OpenYearDecisionForm(forms.ModelForm):
    """القرارُ لعامٍ جارٍ وحدَه — الأعوامُ المغلقة مجمَّدة."""

    def clean(self):
        from .services import ClosedYearError, ExamDecisionService

        data = super().clean()
        school, year = data.get("school"), data.get("academic_year")
        years = {(school, year)}
        if self.instance.pk and self.instance.school_id:
            years.add((self.instance.school, self.instance.academic_year))
        for sch, yr in years:
            if sch is not None and yr:
                try:
                    ExamDecisionService.ensure_open(sch, yr)
                except ClosedYearError as e:
                    raise forms.ValidationError(str(e)) from e
        return data


class _ExamDecisionAdmin(admin.ModelAdmin):
    """الكتابةُ والحذفُ عبر `ExamDecisionService`: سجلُّ المراجعة بقيمتيه، والفاعلُ في
    `decided_by` (لا يُحرَّر باليد)، ثمّ إعادةُ الحكم على الطالب."""

    form = _OpenYearDecisionForm
    readonly_fields = ("decided_by", "created_at")
    list_select_related = ("student", "decided_by", "school")
    search_fields = ("student__full_name",)
    autocomplete_fields = ("student",)

    def save_model(self, request, obj, form, change):
        from .services import ExamDecisionService

        ExamDecisionService.save(obj, request.user)

    def delete_model(self, request, obj):
        from .services import ClosedYearError, ExamDecisionService

        try:
            ExamDecisionService.delete(obj, request.user)
        except ClosedYearError as e:
            messages.error(request, str(e))

    def delete_queryset(self, request, queryset):
        for obj in queryset:
            self.delete_model(request, obj)


@admin.register(ExamDeprivation)
class ExamDeprivationAdmin(_ExamDecisionAdmin):
    """قراراتُ فريق إدارة سلوك الطلبة — الحكمُ (`judge_student`) يقرؤها عند الحفظ."""

    list_display = ("student", "gate", "deprived", "academic_year", "decided_on", "decided_by")
    list_filter = ("gate", "deprived", "school", "academic_year")


@admin.register(ExamMisconduct)
class ExamMisconductAdmin(_ExamDecisionAdmin):
    """وقائعُ لجان الاختبار بمحضر (م47؛ 12: م35) — «غش» في مادّة، و«ملغي» في كلّ الموادّ."""

    list_display = (
        "student",
        "kind",
        "setup",
        "exam",
        "basis",
        "academic_year",
        "decided_on",
        "decided_by",
    )
    list_filter = ("kind", "exam", "basis", "school", "academic_year")
    list_select_related = ("student", "decided_by", "school", "setup__subject")
    raw_id_fields = ("setup",)

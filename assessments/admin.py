from django.contrib import admin
from .models import (
    SubjectClassSetup, AssessmentPackage, Assessment,
    StudentAssessmentGrade, StudentSubjectResult, AnnualSubjectResult,
)


@admin.register(SubjectClassSetup)
class SubjectClassSetupAdmin(admin.ModelAdmin):
    list_display  = ("subject", "class_group", "teacher", "academic_year", "is_active")
    list_filter   = ("school", "academic_year", "is_active")
    search_fields = ("subject__name_ar", "teacher__full_name", "class_group__section")


class AssessmentInline(admin.TabularInline):
    model  = Assessment
    extra  = 0
    fields = ("title", "assessment_type", "date", "max_grade", "weight_in_package", "status")


@admin.register(AssessmentPackage)
class AssessmentPackageAdmin(admin.ModelAdmin):
    list_display = ("get_subject", "get_class", "package_type", "semester",
                    "weight", "semester_max_grade", "effective_max_grade", "is_active")
    list_filter  = ("package_type", "semester", "school", "is_active")
    inlines      = [AssessmentInline]

    def get_subject(self, obj): return obj.setup.subject.name_ar
    def get_class(self, obj):   return str(obj.setup.class_group)
    get_subject.short_description = "المادة"
    get_class.short_description   = "الفصل"


@admin.register(Assessment)
class AssessmentAdmin(admin.ModelAdmin):
    list_display  = ("title", "get_subject", "get_class", "assessment_type",
                     "get_semester", "date", "status", "max_grade")
    list_filter   = ("assessment_type", "status", "school", "package__semester")
    search_fields = ("title", "package__setup__subject__name_ar")

    def get_subject(self, obj):  return obj.subject.name_ar
    def get_class(self, obj):    return str(obj.class_group)
    def get_semester(self, obj): return obj.package.get_semester_display()
    get_subject.short_description  = "المادة"
    get_class.short_description    = "الفصل"
    get_semester.short_description = "الفصل الدراسي"


@admin.register(StudentAssessmentGrade)
class StudentAssessmentGradeAdmin(admin.ModelAdmin):
    list_display  = ("student", "assessment", "grade", "is_absent", "is_excused", "entered_at")
    list_filter   = ("is_absent", "school", "assessment__package__semester")
    search_fields = ("student__full_name", "student__national_id", "assessment__title")
    raw_id_fields = ("student",)


@admin.register(StudentSubjectResult)
class StudentSubjectResultAdmin(admin.ModelAdmin):
    list_display  = ("student", "get_subject", "get_class", "semester",
                     "p1_score", "p2_score", "p3_score", "p4_score",
                     "total", "semester_max")
    list_filter   = ("semester", "school")
    search_fields = ("student__full_name", "student__national_id")
    raw_id_fields = ("student",)

    def get_subject(self, obj): return obj.setup.subject.name_ar
    def get_class(self, obj):   return str(obj.setup.class_group)
    get_subject.short_description = "المادة"
    get_class.short_description   = "الفصل"


@admin.register(AnnualSubjectResult)
class AnnualSubjectResultAdmin(admin.ModelAdmin):
    list_display  = ("student", "get_subject", "get_class", "academic_year",
                     "s1_total", "s2_total", "annual_total", "status", "letter_grade")
    list_filter   = ("status", "school", "academic_year")
    search_fields = ("student__full_name", "student__national_id")
    raw_id_fields = ("student",)

    def get_subject(self, obj):    return obj.setup.subject.name_ar
    def get_class(self, obj):      return str(obj.setup.class_group)
    def letter_grade(self, obj):   return obj.letter_grade
    get_subject.short_description  = "المادة"
    get_class.short_description    = "الفصل"
    letter_grade.short_description = "التقدير"

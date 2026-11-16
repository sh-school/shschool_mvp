"""محدِّدُ قائمة الطلبة الواحد — تستعمله الشاشةُ والتصديرُ معاً فلا يختلف المعروضُ عن المُصدَّر (W-20261109-013).

`student_list_queryset` يطبّق نطاقَ الدور (الجناح) ثمّ الفلترَ كاملاً (البحثُ والصفّ والشعبةُ والحالةُ وحالةُ وليّ الأمر)
لا صفحةَ الترقيم الحاليّة وحدَها. و`rows_for(user, params)` يُرجع صفوفَ الجدول كلَّها بالترتيب المطلوب في الرابط،
بلا `request` فيعمل في عاملِ التصدير كما في الطلب.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from django.db.models import CharField, Exists, F, Func, OuterRef, Q, Subquery, Value

from core.academic_calendar import academic_year_for_school
from core.labels import class_label
from core.models.academic import ClassGroup, ParentStudentLink, StudentEnrollment, Wing
from core.models.access import Membership
from core.privacy import mask_national_id, national_id_search_q
from core.sorting import apply_sort, arabic_key, blank_as_null, normalise_arabic
from wings.scope import StudentScope, student_scope

from .selectors import attach_guardian_phones, guardian_ids_by_phone

#: مفاتيحُ الفرز المصرَّحة. و`?sort=` نصٌّ من المستخدم فلا يبلغ `order_by`
#: إلّا عبر هذه القائمة. وكلُّها تنتهي بالاسم فاصلاً يقطع التساوي.
STUDENT_SORTS = {
    "name": ("name_key",),
    "national": ("national_key", "name_key"),
    # الصفُّ والشعبةُ عمودٌ واحدٌ يُعرض، فمفتاحُهما واحدٌ يُفرَز.
    "class": ("grade_key", "section_key", "name_key"),
    "guardian": ("guardian_key", "name_key"),
}


def list_status(scope: StudentScope, params: Any) -> str:
    """حالةُ القيد المعروضة: المقيَّدُ بجناحه لا يرى إلّا المقيَّدين (طالبٌ بلا قيدٍ نشطٍ لا جناحَ له)."""
    return "enrolled" if scope.is_wing_bound else (params.get("status") or "enrolled")


def wing_options(scope: StudentScope, school: Any, year: str) -> list[tuple[str, str]]:
    """خياراتُ فلتر الجناح `[(المعرّف, الاسم)]` بترتيب الأجنحة، من شُعب نطاق الدور وحدَها."""
    groups = scope.narrow_classes(
        ClassGroup.objects.filter(
            school=school, academic_year=year, is_active=True, wing__isnull=False
        ),
        "pk",
    )
    wings = Wing.objects.filter(pk__in=groups.values("wing_id")).order_by("order")
    return [(str(w.pk), w.name) for w in wings]


def filter_context(scope: StudentScope, school: Any, year: str, params: Any) -> dict[str, Any]:
    """قيمُ حقول الفلتر وخياراتُ الجناح للقالب؛ المقيَّدُ بجناحه لا يحتاج فلترَ الجناح."""
    return {
        "q": params.get("q", "").strip(),
        "grade_filter": params.get("grade", ""),
        "section_filter": params.get("section", ""),
        "parent_status": params.get("parent_status", ""),
        "wing_filter": params.get("wing", ""),
        "wings": [] if scope.is_wing_bound else wing_options(scope, school, year),
    }


def year_in_scope(scope: StudentScope, params: Any, current: str) -> str:
    """العامُ المعروض — `?year=` لغير المقيَّد، والمقيَّدُ بجناحه على عامه الجاري فلا يوسّع الرابطُ نطاقَه."""
    requested = params.get("year")
    if requested and not scope.is_wing_bound:
        return str(requested)
    return scope.year_for(requested, scope.year or current)


def student_list_queryset(
    user: Any, school: Any, scope: StudentScope, year: str, params: Any
) -> Any:
    """طلبةُ الشاشة بعد النطاق والفلتر وقبل الفرز والترقيم — الصفُّ والشعبةُ والجناحُ مُلحَقةٌ على الاستعلام."""
    students = scope.narrow(
        Membership.objects.filter(school=school, role__name="student", is_active=True)
        .select_related("user", "user__profile")
        .order_by("user__full_name"),
        "user_id",
    )

    q = params.get("q", "").strip()
    grade_filter = params.get("grade", "")
    section_filter = params.get("section", "")
    parent_status = params.get("parent_status", "")

    # الجناحُ يُرشَّح بمعرّفه (`class_group__wing_id`) لا باسمه، وبعد نطاق الدور فلا يوسّعه.
    for field, wanted in (
        ("grade", grade_filter),
        ("section", section_filter),
        ("wing_id", params.get("wing", "")),
    ):
        if wanted:
            students = students.filter(
                Exists(
                    scope.narrow_classes(
                        StudentEnrollment.objects.filter(
                            **{
                                "class_group__school": school,
                                "class_group__academic_year": year,
                                f"class_group__{field}": wanted,
                                "is_active": True,
                                "student_id": OuterRef("user_id"),
                            }
                        )
                    )
                )
            )

    if parent_status in ("linked", "unlinked"):
        has_parent = Exists(
            ParentStudentLink.objects.filter(school=school, student_id=OuterRef("user_id"))
        )
        students = students.annotate(_has_parent=has_parent).filter(
            _has_parent=parent_status == "linked"
        )

    # المقيَّدُ أوّلاً: العضويّةُ تقول «طالبُ المدرسة» والقيدُ يقول «صفُّه هذا العام» — وهما شيئان.
    status = list_status(scope, params)
    is_enrolled = Exists(
        StudentEnrollment.objects.filter(
            student_id=OuterRef("user_id"),
            class_group__school=school,
            class_group__academic_year=year,
            is_active=True,
        )
    )
    if status == "enrolled":
        students = students.filter(is_enrolled)
    elif status == "unenrolled":
        students = students.exclude(is_enrolled)

    # الصفُّ والشعبةُ صفتا قيدٍ لا صفتا شخص، فتُجلبان بالاستعلام نفسِه ليصحّ الفرزُ على السجلّ كلِّه لا على الصفحة.
    enrolment = scope.narrow_classes(
        StudentEnrollment.objects.filter(
            student_id=OuterRef("user_id"), class_group__academic_year=year, is_active=True
        )
    ).order_by("-class_group__academic_year", "-enrolled_at")
    guardian = ParentStudentLink.objects.filter(
        student_id=OuterRef("user_id"), school=school
    ).order_by("-is_primary", "created_at")

    students = students.annotate(
        grade_code=Subquery(enrolment.values("class_group__grade")[:1]),
        section_code=Subquery(enrolment.values("class_group__section")[:1]),
        # ترتيبُ الجناح (1..5) لفرز التصدير بالجناح — `core/dept_colors.WING_KEY_OF_ORDER`.
        wing_order=Subquery(enrolment.values("class_group__wing__order")[:1]),
        name_key=arabic_key(F("user__full_name")),
        national_key=blank_as_null("user__national_id"),
        # وليُّ الأمر: الأساسيُّ أوّلاً، فإن لم يُعلَّم أحدٌ فأقدمُ ارتباط.
        guardian_name=Subquery(guardian.values("parent__full_name")[:1]),
        guardian_parent_id=Subquery(guardian.values("parent_id")[:1]),
        guardian_relation=Subquery(guardian.values("relationship")[:1]),
    ).annotate(
        # «G10» نصّاً يسبق «G7»، وعدداً يليه: تُنزع الحروفُ ويُحشى الرقمُ بصفرٍ فيصير ترتيبُ الحروف ترتيبَ الأعداد.
        grade_key=Func(
            Func(
                F("grade_code"),
                Value(r"\D"),
                Value(""),
                Value("g"),
                function="REGEXP_REPLACE",
                output_field=CharField(),
            ),
            Value(2),
            Value("0"),
            function="LPAD",
            output_field=CharField(),
        ),
        section_key=blank_as_null("section_code"),
        guardian_key=arabic_key(F("guardian_name")),
    )

    # والبحثُ على الرقم **الكامل** لا المستور: من كتب رقماً كاملاً وجد صاحبَه وإن عُرض ذيلُه وحدَه.
    if q:
        shaped = normalise_arabic(q)
        students = students.filter(
            Q(name_key__icontains=shaped)
            | national_id_search_q("user__national_id", q, user=user)
            | Q(guardian_key__icontains=shaped)
            | Q(guardian_parent_id__in=guardian_ids_by_phone(school, q))
            | Q(grade_code__icontains=q)
            | Q(section_code__icontains=q)
        )
    return students


def rows_for(user: Any, params: Any) -> list[dict[str, Any]]:
    """صفوفُ جدول قائمة الطلبة كلُّها بعد نطاق الدور والفلتر، بترتيب `?sort=` — محدِّدُ الشاشة والتصدير الواحد.

    الرقمُ الشخصيُّ مستورٌ كما في الشاشة، وجوّالُ وليّ الأمر كما تعرضه.
    """
    school = user.get_school()
    scope = student_scope(user, school)
    year = year_in_scope(scope, params, academic_year_for_school(school))
    students = student_list_queryset(user, school, scope, year, params)
    students, _sort = apply_sort(
        students, SimpleNamespace(GET=params), allowed=STUDENT_SORTS, default="name"
    )
    relations = dict(ParentStudentLink._meta.get_field("relationship").choices)
    members = attach_guardian_phones(list(students))
    return [
        {
            "id": m.user_id,
            "full_name": m.user.full_name,
            "national_id": mask_national_id(m.user.national_id),
            "class_label": class_label(m.grade_code, m.section_code),
            "guardian_name": m.guardian_name or "",
            "guardian_phone": m.guardian_phone,
            "guardian_relation": relations.get(m.guardian_relation, ""),
            "wing_order": m.wing_order,
        }
        for m in members
    ]

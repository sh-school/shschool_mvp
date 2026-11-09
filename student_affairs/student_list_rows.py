"""محدِّدُ قائمة الطلبة الواحد — تستعمله الصفحةُ والتصديرُ معاً فلا يختلف المعروضُ عن المُصدَّر (W-20261109-012).

بلا `request`: يعمل في الطلب وفي عاملِ التصدير. نطاقُ الدور (جناحُ المشرف) يُطبَّق على الاستعلام الأساسيّ **قبل** كلِّ
مرشِّحٍ وفرزٍ وترقيم، والفلترُ كاملٌ (`q` والصفُّ والشعبةُ والحالةُ وحالةُ وليّ الأمر) لا صفحةُ الترقيم وحدَها.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from django.db.models import CharField, Exists, F, Func, OuterRef, Q, Subquery, Value

from core.academic_calendar import academic_year_for_school
from core.exports.contract import sort_by_wing
from core.labels import class_label
from core.models.academic import ParentStudentLink, StudentEnrollment
from core.models.access import Membership
from core.privacy import mask_national_id, national_id_search_q
from core.sorting import apply_sort, arabic_key, blank_as_null, normalise_arabic
from wings.scope import student_scope

from .selectors import attach_guardian_phones, guardian_ids_by_phone

#: مفاتيحُ الفرز المصرَّحة. و`?sort=` نصٌّ من المستخدم فلا يبلغ `order_by` إلّا عبر هذه القائمة.
#: وكلُّها تنتهي بالاسم فاصلاً يقطع التساوي.
STUDENT_SORTS = {
    "name": ("name_key",),
    "national": ("national_key", "name_key"),
    # الصفُّ والشعبةُ عمودٌ واحدٌ يُعرض، فمفتاحُهما واحدٌ يُفرَز.
    "class": ("grade_key", "section_key", "name_key"),
    "guardian": ("guardian_key", "name_key"),
}


def year_in_scope(scope: Any, params: Any, default: str) -> str:
    """العامُ المعروض — `?year=` لغير المقيَّد، والمقيَّدُ بجناحه على عامه الجاري (`StudentScope.year_for`)."""
    requested = params.get("year")
    if requested and not scope.is_wing_bound:
        return str(requested)
    return str(scope.year_for(requested, scope.year or default))


def status_of(scope: Any, params: Any) -> str:
    """المقيَّدُ بجناحه لا يرى إلّا المقيَّدين: طالبٌ بلا قيدٍ نشطٍ لا جناحَ له."""
    return "enrolled" if scope.is_wing_bound else str(params.get("status") or "enrolled")


def _filtered(school: Any, year: str, scope: Any, params: Any) -> Any:
    """الطلبةُ بعد النطاق والصفِّ والشعبةِ وحالةِ وليّ الأمر والقيد."""
    students = scope.narrow(
        Membership.objects.filter(school=school, role__name="student", is_active=True)
        .select_related("user", "user__profile")
        .order_by("user__full_name"),
        "user_id",
    )

    def in_class(**field: str) -> Any:
        return Exists(
            scope.narrow_classes(
                StudentEnrollment.objects.filter(
                    class_group__school=school,
                    class_group__academic_year=year,
                    is_active=True,
                    student_id=OuterRef("user_id"),
                    **field,
                )
            )
        )

    if params.get("grade"):
        students = students.filter(in_class(class_group__grade=params["grade"]))
    if params.get("section"):
        students = students.filter(in_class(class_group__section=params["section"]))

    parent_status = params.get("parent_status", "")
    if parent_status in ("linked", "unlinked"):
        has_parent = Exists(
            ParentStudentLink.objects.filter(school=school, student_id=OuterRef("user_id"))
        )
        students = students.annotate(_has_parent=has_parent).filter(
            _has_parent=parent_status == "linked"
        )

    # المقيَّدُ أوّلاً، ومن أُغلق قيدُه لا يسقط بل يُرشَّح.
    status = status_of(scope, params)
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
    return students


def _annotated(school: Any, year: str, scope: Any, students: Any) -> Any:
    """الصفُّ والشعبةُ صفتا قيدٍ لا صفتا شخص: تُجلبان بالاستعلام نفسِه ليصحّ الفرزُ بهما على السجلّ كلِّه."""
    enrolment = scope.narrow_classes(
        StudentEnrollment.objects.filter(
            student_id=OuterRef("user_id"), class_group__academic_year=year, is_active=True
        )
    ).order_by("-class_group__academic_year", "-enrolled_at")
    guardian = ParentStudentLink.objects.filter(
        student_id=OuterRef("user_id"), school=school
    ).order_by("-is_primary", "created_at")

    return students.annotate(
        grade_code=Subquery(enrolment.values("class_group__grade")[:1]),
        section_code=Subquery(enrolment.values("class_group__section")[:1]),
        wing_order=Subquery(enrolment.values("class_group__wing__order")[:1]),
        name_key=arabic_key(F("user__full_name")),
        national_key=blank_as_null("user__national_id"),
        # وليُّ الأمر: الأساسيُّ أوّلاً، فإن لم يُعلَّم أحدٌ فأقدمُ ارتباط.
        guardian_name=Subquery(guardian.values("parent__full_name")[:1]),
        guardian_parent_id=Subquery(guardian.values("parent_id")[:1]),
        guardian_relation=Subquery(guardian.values("relationship")[:1]),
    ).annotate(
        # «G10» نصّاً يسبق «G7»: تُنزع الحروفُ ويُحشى الرقمُ بصفرٍ فيصير ترتيبُ الحروف ترتيبَ الأعداد.
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


def student_list_queryset(
    user: Any, school: Any, year: str, scope: Any, params: Any
) -> tuple[Any, Any]:
    """`(الطلبةُ بالفلتر والفرز كاملين، حالةُ الفرز)` — بلا ترقيم."""
    students = _annotated(school, year, scope, _filtered(school, year, scope, params))
    # والبحثُ يقع على الرقم **الكامل** لا على المستور.
    q = (params.get("q") or "").strip()
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
    return apply_sort(students, SimpleNamespace(GET=params), allowed=STUDENT_SORTS, default="name")


def row_dicts(page: Any) -> list[dict[str, Any]]:
    """صفوفُ الجدول كما تُعرض — الصفحةُ والتصديرُ يبنيانها من هذه الدالّة وحدَها."""
    relations = dict(ParentStudentLink._meta.get_field("relationship").choices)
    return [
        {
            "id": m.user_id,
            "full_name": m.user.full_name,
            # آخرُ أربعِ خاناتٍ وما قبلها مستور: القارئُ يحتاج أن يميّز لا أن يعرف.
            "national_id": mask_national_id(m.user.national_id),
            # «07/2» كما تكتبه الوزارة — عمودٌ واحدٌ لا عمودان.
            "class_label": class_label(m.grade_code, m.section_code),
            "guardian_name": m.guardian_name or "",
            "guardian_phone": m.guardian_phone,
            "guardian_relation": relations.get(m.guardian_relation, ""),
            "can_sign_in": m.user.is_active and m.user.has_usable_password(),
            "wing_order": m.wing_order,
        }
        for m in page
    ]


def rows_for(user: Any, params: Any, school: Any = None) -> list[dict[str, Any]]:
    """كلُّ صفوف القائمة المعروضة لهذا المستخدم بهذه المعاملات — لا صفحةَ الترقيم الحاليّة وحدَها.

    الفرزُ بالجناح (`WING_KEY_OF_ORDER`) لمن لم يطلب فرزاً صريحاً، مستقرٌّ فيبقى الاسمُ فاصلاً داخل الجناح.
    """
    school = school or user.get_school()
    scope = student_scope(user, school)
    year = year_in_scope(scope, params, academic_year_for_school(school))
    students, _sort = student_list_queryset(user, school, year, scope, params)
    rows = row_dicts(attach_guardian_phones(list(students)))
    return rows if params.get("sort") else sort_by_wing(rows)

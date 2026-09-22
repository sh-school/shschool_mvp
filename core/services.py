"""خدماتُ النواة — استيرادُ الطلاب وأولياء الأمور من Excel (الكتابةُ خارج العرض).

الكلماتُ الأوّليّةُ الصادرةُ تبقى في قائمةٍ في الذاكرة يعيدها الاستيرادُ لعرضها في
استجابةٍ واحدة؛ لا تُخزَّن ولا تُسجَّل — ويُسجَّل عددُها وحده أثراً.
"""

from __future__ import annotations

import logging
from typing import Any

from django.db import transaction

from core.academic_calendar import academic_year_for_school

logger = logging.getLogger(__name__)

# ── ثوابت الاستيراد ──────────────────────────────────────────────────

_IMPORT_RELATION_MAP: dict[str, str] = {
    "father": "father",
    "mother": "mother",
    "guardian": "guardian",
    "other": "other",
    "أب": "father",
    "والد": "father",
    "أم": "mother",
    "ام": "mother",
    "والدة": "mother",
    "وصي": "guardian",
    "وصية": "guardian",
}

_IMPORT_GRADE_NORMALIZE = {
    "7": "G7",
    "8": "G8",
    "9": "G9",
    "10": "G10",
    "11": "G11",
    "12": "G12",
    "g7": "G7",
    "g8": "G8",
    "g9": "G9",
    "g10": "G10",
    "g11": "G11",
    "g12": "G12",
    "G7": "G7",
    "G8": "G8",
    "G9": "G9",
    "G10": "G10",
    "G11": "G11",
    "G12": "G12",
}


# ── مساعدات الاستيراد ─────────────────────────────────────────────────


def _split_class_notation(grade_cell: str, section_cell: str) -> tuple[str, str]:
    """يقبل «7/1» في خانة الصف كما يقبل عمودين منفصلين.

    الشُّعب في المدرسة تُسمّى «7/1» و«11/2» — اسمٌ واحد لا حقلان. وكان
    الاستيراد يتوقّع عمودين، فخانةٌ مكتوبٌ فيها «7/1» لا تُطابق مفتاحاً في
    `_IMPORT_GRADE_NORMALIZE`، فيُتخطّى الطالب بلا تسجيل.

    ولا يُخفق الاستيراد: يُنشئ الطالب ويُدرج سطراً في الأخطاء، فيسهل أن يمرّ
    مئةُ طالبٍ بلا شعبة دون أن ينتبه أحد.

    فإن حوت خانة الصف فاصلاً (‏/ أو . أو -) قُسّمت، وإلّا بقي العمودان كما هما.
    """
    if section_cell:
        return grade_cell, section_cell
    for sep in ("/", ".", "-"):
        if sep in grade_cell:
            head, _, tail = grade_cell.partition(sep)
            return head.strip(), tail.strip()
    return grade_cell, section_cell


def _parse_import_row(row: Any) -> dict[str, str]:
    """يحوّل tuple الصف الخام إلى قاموس بأسماء واضحة."""

    def _cell(pos: int, default: str = "") -> str:
        return str(row[pos]).strip() if len(row) > pos and row[pos] else default

    grade_raw, section = _split_class_notation(_cell(2), _cell(3))

    return {
        "student_nid": _cell(0),
        "full_name": _cell(1),
        "grade_raw": grade_raw,
        "section": section,
        "phone": _cell(4),
        "email": _cell(5),
        "parent_nid": _cell(6),
        "parent_name": _cell(7),
        "parent_phone": _cell(8),
        "parent_email": _cell(9),
        "relation_raw": _cell(10, "father"),
    }


def _upsert_user(
    nid: str,
    full_name: str,
    phone: str = "",
    email: str = "",
    *,
    role_label: str = "",
    issued: list[dict] | None = None,
) -> tuple[Any, bool]:
    """
    get_or_create مستخدم بالرقم الشخصي.
    إذا أُنشئ: كلمةُ مرورٍ عشوائيّةٌ (قرارُ المالك: لا تساوي الرقمَ الشخصيّ) مع
    `must_change_password`، ويملأ phone/email.
    إذا كان موجوداً: يُكمل الحقول الفارغة فقط ولا يمسّ كلمتَه.
    يُعيد (user, created).

    `issued`: قائمةُ المستدعي — يُضاف إليها صفُّ ورقةِ الاعتماد للحساب الجديد
    (الرقمُ مستورٌ: كشفٌ جماعيّ). الكلمةُ لا تُحفظ في غير هذه القائمة في الذاكرة.
    """
    from core.initial_passwords import assign_initial_password
    from core.models import CustomUser

    user: Any
    user, created = CustomUser.objects.get_or_create(
        national_id=nid,
        defaults={"full_name": full_name or nid, "is_active": True},
    )
    if created:
        assign_initial_password(user, issued if issued is not None else [], role_label)
        if phone:
            user.phone = phone
        if email:
            user.email = email
        user.save()
    else:
        changed = False
        if not user.full_name and full_name:
            user.full_name = full_name
            changed = True
        if not user.phone and phone:
            user.phone = phone
            changed = True
        if not user.email and email:
            user.email = email
            changed = True
        if changed:
            user.save()
    return user, created


def _enroll_student_in_class(
    student: Any,
    school: Any,
    grade_raw: str,
    section: str,
    stats: dict[str, Any],
    row_num: int,
) -> bool:
    """
    يبحث عن الفصل ويسجّل الطالب فيه.
    يُضيف خطأ إلى stats إذا لم يُعثر على الفصل.
    يُعيد True إذا أُنشئ تسجيل جديد.
    """
    from core.models import ClassGroup, StudentEnrollment

    grade = _IMPORT_GRADE_NORMALIZE.get(grade_raw, "")
    if not (grade and section):
        return False

    # الشُّعب مرتبطةٌ بعامها، فمع وجود عامين تُعيد `first()` واحدةً عشوائية —
    # ويُسجَّل الطالب في شعبة العام الماضي. والتقييد بالعام يمنع ذلك.
    year = academic_year_for_school(school)
    class_group = ClassGroup.objects.filter(
        school=school, grade=grade, section=section, academic_year=year, is_active=True
    ).first()

    if not class_group:
        stats["errors"].append(
            f"سطر {row_num}: الفصل {grade}/{section} غير موجود في {year} "
            f"— تم إنشاء الطالب بدون تسجيل"
        )
        return False

    _, created = StudentEnrollment.objects.get_or_create(
        student=student, class_group=class_group, defaults={"is_active": True}
    )
    return bool(created)


def _link_parent_to_student(
    parent: Any, student: Any, school: Any, relation_raw: str, stats: dict[str, Any]
) -> bool:
    """
    يُنشئ ParentStudentLink إذا لم يكن موجوداً.
    يُعيد True إذا أُنشئ رابط جديد.
    """
    from core.models import ParentStudentLink

    relation = _IMPORT_RELATION_MAP.get(relation_raw, "father")
    _, created = ParentStudentLink.objects.get_or_create(
        parent=parent,
        student=student,
        school=school,
        defaults={
            "relationship": relation,
            "is_primary": True,
            "can_view_grades": True,
            "can_view_attendance": True,
        },
    )
    return created


def process_student_import(uploaded_file: Any, school: Any, year: Any) -> dict[str, Any]:
    """
    يقرأ ملف Excel ويستورد الطلاب + أولياء الأمور.
    يُعيد dict بإحصائيات النتيجة + قائمة الأخطاء.
    """
    import openpyxl

    from core.models import Membership, Role

    roles = {r.name: r for r in Role.objects.all()}
    student_role = roles.get("student")
    parent_role = roles.get("parent")

    if not student_role or not parent_role:
        return {
            "success": False,
            "errors": ["الأدوار الأساسية (student/parent) غير موجودة — شغّل seed_data أولاً."],
        }

    wb = openpyxl.load_workbook(uploaded_file, read_only=True, data_only=True)
    ws = wb.active

    # فلترة صفوف البيانات الصالحة (تجاوز الرأس والتعليقات)
    data_rows = []
    for row in ws.iter_rows(min_row=2, values_only=True):
        if not row or not row[0]:
            continue
        first = str(row[0]).strip()
        if first.startswith("#") or not first[0].isdigit():
            continue
        data_rows.append(row)

    stats: dict[str, Any] = {
        "students_created": 0,
        "students_existed": 0,
        "parents_created": 0,
        "parents_existed": 0,
        "enrollments_created": 0,
        "links_created": 0,
        "errors": [],
    }
    # ورقةُ الاعتماد: في الذاكرة وحدَها، تُعرض في استجابة هذا الطلب ثمّ تزول.
    issued: list[dict] = []

    with transaction.atomic():
        for i, raw_row in enumerate(data_rows, start=2):
            fields = _parse_import_row(raw_row)

            if not fields["student_nid"]:
                stats["errors"].append(f"سطر {i}: الرقم الشخصي فارغ — تجاوز")
                continue
            if not fields["full_name"]:
                stats["errors"].append(f"سطر {i}: اسم الطالب {fields['student_nid']} فارغ — تجاوز")
                continue

            # ── الطالب ──────────────────────────────────────────────
            student, s_created = _upsert_user(
                fields["student_nid"],
                fields["full_name"],
                fields["phone"],
                fields["email"],
                role_label="طالب",
                issued=issued,
            )
            stats["students_created" if s_created else "students_existed"] += 1

            if school:
                Membership.objects.get_or_create(
                    user=student,
                    school=school,
                    role=student_role,
                    defaults={"is_active": True},
                )
                if _enroll_student_in_class(
                    student, school, fields["grade_raw"], fields["section"], stats, i
                ):
                    stats["enrollments_created"] += 1

            # ── ولي الأمر (اختياري) ──────────────────────────────────
            if not fields["parent_nid"]:
                continue

            parent, p_created = _upsert_user(
                fields["parent_nid"],
                fields["parent_name"],
                fields["parent_phone"],
                fields["parent_email"],
                role_label="ولي أمر",
                issued=issued,
            )
            stats["parents_created" if p_created else "parents_existed"] += 1

            if school:
                Membership.objects.get_or_create(
                    user=parent,
                    school=school,
                    role=parent_role,
                    defaults={"is_active": True},
                )
                if _link_parent_to_student(parent, student, school, fields["relation_raw"], stats):
                    stats["links_created"] += 1

    return {
        "success": True,
        "total_rows": len(data_rows),
        "students_created": stats["students_created"],
        "students_existed": stats["students_existed"],
        "parents_created": stats["parents_created"],
        "parents_existed": stats["parents_existed"],
        "enrollments_created": stats["enrollments_created"],
        "links_created": stats["links_created"],
        "error_count": len(stats["errors"]),
        "errors": stats["errors"][:20],
        # كلماتُ مرورٍ نصّيّةٌ — للعرض في استجابةٍ واحدةٍ فقط؛ لا تُخزَّن ولا تُسجَّل.
        "credentials": issued,
    }


def _audit_credentials_issued(user: Any, school: Any, count: int) -> None:
    """يترك أثراً بأنّ كلماتِ مرورٍ صدرت — **العددُ** لا الكلمات ولا أصحابُها."""
    from core.models.audit import AuditLog

    AuditLog.objects.create(
        school=school,
        user=user,
        action="update",
        model_name="other",
        object_id="",
        object_repr=f"استيرادُ الطلاب: صدرت {count} كلمةَ مرورٍ أوّليّة"[:300],
        changes={
            "event": "import_initial_passwords_issued",
            "count": count,
            "must_change_password": True,
        },
    )


def import_result_context(user: Any, school: Any, result: dict[str, Any]) -> dict:
    """ما يُضاف إلى سياق الصفحة من نتيجة الاستيراد: ورقةُ الاعتماد وعدّادُ الأخطاء.

    ورقةُ الاعتماد تُعرض في هذه الاستجابة وحدَها؛ وصفحةٌ للمسجَّل بلا تخزين
    (`PrivateHtmlNoStoreMiddleware`) فلا تبقى في المتصفّح.
    """
    extra: dict = {}
    if result.get("credentials"):
        extra["credentials"] = result["credentials"]
        try:
            _audit_credentials_issued(user, school, len(result["credentials"]))
        except Exception:  # noqa: BLE001 — فشلُ الأثر لا يُضيّع ورقةً لا تُعاد
            logger.exception("تعذّر تسجيل أثر إصدار كلمات المرور")
    # الأخطاءُ تُعرض عشرين، وما بقي يُقال عدداً؛ والكهرمانيُّ حين يوجد خطأ
    # (العتبةُ التي كانت في القالب: أكبرُ من صفر).
    error_count = result.get("error_count", len(result.get("errors", [])))
    extra["errors_more"] = max(0, error_count - len(result.get("errors", [])))
    extra["errors_tone"] = "amber" if error_count > 0 else "green"
    return extra


def count_active_students(school: Any) -> int:
    """عددُ الطلاب الفاعلين في المدرسة (عضويّةٌ بدور student)."""
    from core.models import Membership, Role

    student_role = Role.objects.filter(name="student").first()
    if not (school and student_role):
        return 0
    return Membership.objects.filter(school=school, role=student_role, is_active=True).count()


# ── إعادةُ تعيين كلمات مرور المستخدمين (فنّي تقنية المعلومات) ────────────


def school_users(school: Any, q: str = "") -> Any:
    """مستخدمو مدرسةٍ للبحث والعرض — `search_simple` عند وجود استعلام."""
    from core.models import CustomUser

    people = CustomUser.objects.filter(memberships__school=school).distinct().order_by("full_name")
    if not q:
        return people
    # django-stubs لا يعرف UserQuerySet خلف CustomUserManager — search_simple موجودةٌ فعلاً (core/querysets.py).
    return people.search_simple(q)  # type: ignore[attr-defined]


def reset_user_password(*, school: Any, target_id: Any, actor: Any) -> tuple[Any, str]:
    """يعيد تعيين كلمةَ مرور مستخدمٍ في مدرسة الفاعل — كلمةٌ عشوائيّة (لا حقلَ حرّ)،
    تُلزمه بتغييرها عند الدخول التالي، وتُسجَّل في AuditLog بلا القيمة نفسها.

    يرفع `Http404` إن لم يكن المستخدَمُ عضواً في مدرسة الفاعل — لا تسريبَ بين المدارس.
    """
    from django.shortcuts import get_object_or_404

    from core.initial_passwords import make_initial_password
    from core.models import AuditLog, CustomUser

    target = get_object_or_404(
        CustomUser.objects.filter(memberships__school=school).distinct(), id=target_id
    )
    new_password = make_initial_password()
    with transaction.atomic():
        target.set_password(new_password)
        target.must_change_password = True
        target.save(update_fields=["password", "must_change_password"])
        AuditLog.objects.create(
            school=school,
            user=actor,
            action="update",
            model_name="CustomUser",
            object_id=str(target.id),
            object_repr=f"إعادة تعيين كلمة مرور: {target.full_name}"[:300],
        )
    return target, new_password

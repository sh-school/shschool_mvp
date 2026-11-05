"""قراءاتُ شؤون الطلبة التي يشترك فيها أكثرُ من مسار — بلا `request` فتعمل في العامل كما في الطلب."""

from __future__ import annotations

import datetime as dt
from typing import Any

from django.core.exceptions import ValidationError
from django.db.models import Exists, OuterRef, Q

from core.academic_calendar import academic_year_for_school
from core.domain.attendance import attendance_rate
from core.models.academic import ClassGroup, ParentStudentLink, StudentEnrollment
from core.models.access import Membership
from core.models.user import CustomUser
from core.phone_search import phone_holder_ids
from core.privacy import national_id_search_q


def student_register(
    school: Any, year: str, params: Any, *, partial_id: bool = False
) -> tuple[Any, dict[int, dict[str, Any]]]:
    """الاستعلامُ المشترَك بين تصديرَي سجلّ الطلاب — Excel وPDF: `(الطلبة، القيدُ لكلّ طالب)`.

    نفس فلترة `student_list`، بما فيها الإصلاحُ الذي أخذته الشاشةُ في #191 ولم
    يكن قد بلغ أيَّ تصدير: المقيَّدُ أوّلاً، ومن لا قيدَ له هذا العامَ يخرج
    بترشيحٍ صريحٍ (`status=unenrolled` أو `all`) لا بعدٍّ يُساوي به العضويّةَ
    بالقيد.

    `params` هو `QueryDict` الرابط (`request.GET`)؛ والعامُ يُمرَّر لا يُشتقّ هنا كي يبقى النداءُ نقيّاً.
    """
    q = params.get("q", "").strip()
    grade_filter = params.get("grade", "")
    section_filter = params.get("section", "")

    students = (
        Membership.objects.filter(
            school=school,
            role__name="student",
            is_active=True,
        )
        .select_related("user")
        .order_by("user__full_name")
    )

    if q:
        students = students.filter(
            Q(user__full_name__icontains=q)
            | national_id_search_q("user__national_id", q, partial=partial_id)
        )

    status = params.get("status") or "enrolled"
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

    enrollment_data: dict[int, dict[str, Any]] = {}
    for enr in StudentEnrollment.objects.filter(
        class_group__school=school,
        class_group__academic_year=year,
        is_active=True,
    ).values("student_id", "class_group__grade", "class_group__section"):
        enrollment_data[enr["student_id"]] = enr

    if grade_filter:
        enrolled_ids = [
            sid
            for sid, data in enrollment_data.items()
            if data["class_group__grade"] == grade_filter
        ]
        students = students.filter(user_id__in=enrolled_ids)
    if section_filter:
        enrolled_ids = [
            sid
            for sid, data in enrollment_data.items()
            if data.get("class_group__section") == section_filter
        ]
        students = students.filter(user_id__in=enrolled_ids)

    return students, enrollment_data


def guardian_ids_by_phone(school: Any, term: str) -> list:
    """معرّفاتُ أولياء الأمر في المدرسة ممّن يحوي جوّالُه الأرقامَ المكتوبة — بلا قراءةٍ للعمود الصريح."""
    parents = CustomUser.objects.filter(
        pk__in=ParentStudentLink.objects.filter(school=school).values("parent_id")
    )
    return list(phone_holder_ids(parents, term))


def guardian_phones(parent_ids: Any) -> dict:
    """{معرّفُ وليّ الأمر: جوّالُه} لمن في الصفحة وحدَهم."""
    ids = {pk for pk in parent_ids if pk}
    users = CustomUser.objects.filter(pk__in=ids).only("pk", "phone", "phone_encrypted")
    return {u.pk: u.get_phone_decrypted() for u in users}


def attach_guardian_phones(page: Any) -> Any:
    """يضع `guardian_phone` على كلّ صفٍّ في الصفحة من النسخة المشفَّرة، ويُرجع الصفحةَ نفسَها."""
    phones = guardian_phones(m.guardian_parent_id for m in page)
    for m in page:
        m.guardian_phone = phones.get(m.guardian_parent_id, "")
    return page


def transfer_form_options(school: Any) -> tuple[list, Any]:
    """خياراتُ نموذج الانتقال: كلُّ طالبٍ بصفّه وشعبته (استعلامٌ واحدٌ للقيود)، وكلُّ شعبةٍ نشطةٍ هدفاً داخليّاً."""
    students = list(
        Membership.objects.filter(school=school, role__name="student", is_active=True)
        .select_related("user")
        .order_by("user__full_name")
    )
    current: dict = {}
    for enrollment in (
        StudentEnrollment.objects.filter(
            student_id__in=[m.user_id for m in students],
            class_group__school=school,
            is_active=True,
        )
        .select_related("class_group")
        .newest_first()
    ):
        current.setdefault(enrollment.student_id, enrollment.class_group)
    for membership in students:
        klass = current.get(membership.user_id)
        membership.class_grade = klass.grade if klass else ""
        membership.class_id = klass.pk if klass else ""
        membership.class_label = klass.short_label if klass else "بلا شعبة"
    return students, ClassGroup.objects.filter(
        school=school, is_active=True, academic_year=academic_year_for_school(school)
    )


def active_class(school: Any, class_id: Any) -> Any:
    """الشعبةُ النشطة في المدرسة بمعرّفها، أو `None`."""
    return ClassGroup.objects.filter(id=class_id, school=school, is_active=True).first()


#: حصّتا الجرس الأولى والثانية — العدّادُ والنسبةُ ومعهما راصدُ الغياب من تعريفٍ واحد.
EARLY_PERIODS = (1, 2)


def early_attendance_counts(school: Any, day: Any, scope: Any) -> dict[str, Any]:
    """حاضرو اليوم وغائبوه من حضور الحصّتين الأولى والثانية، مجمَّعين بالجناح ثمّ الشعبة.

    من حضر إحدى الحصّتين (حاضرٌ أو متأخّر) فهو حاضر، والغائبُ من غاب عنهما معاً
    (قرار المالك 2026-10-09)؛ والطالبُ يُعدّ مرّةً واحدةً لا بعدد سجلّاته. المصدر:
    `Session.period_number` لليوم، والمقيَّدُ بجناحه يمرّ على `scope.narrow` قبل التجميع.
    قبل رصد أيّ من الحصّتين: `pct` فارغة (None) لا صفر. الجدولُ المعتمدُ لا يُقرأ هنا
    ولا يُحكم بـ`_judge` — هذه قراءةُ عرضٍ لا حكمُ حرمان.
    """
    from operations.absence_standing import ATTENDED
    from operations.models import StudentAttendance

    rows = (
        scope.narrow(
            StudentAttendance.objects.filter(
                school=school,
                session__date=day,
                session__period_number__in=EARLY_PERIODS,
            )
        )
        .values_list(
            "student_id",
            "status",
            "excuse_type",
            "session__class_group_id",
            "session__class_group__wing_id",
            "session__class_group__wing__name",
            "session__class_group__grade",
            "session__class_group__section",
        )
        .order_by()
    )
    students: dict[Any, dict[str, Any]] = {}
    for student, status, excuse, section, wing, wing_name, grade, code in rows:
        entry = students.setdefault(
            student,
            {
                "section": section,
                "wing": wing,
                "wing_name": wing_name or "",
                "grade": grade,
                "code": code,
                "attended": False,
                "late": False,
                "unexcused": False,
            },
        )
        if status in ATTENDED:
            entry["attended"] = True
            entry["late"] = entry["late"] or status == "late"
        elif status == "absent" and not excuse:
            entry["unexcused"] = True

    def blank() -> dict[str, int]:
        return {"total": 0, "present": 0, "absent": 0, "late": 0, "excused": 0}

    total = blank()
    wings: dict[Any, dict[str, Any]] = {}
    for entry in students.values():
        wing = wings.setdefault(
            entry["wing"],
            {"name": entry["wing_name"] or "بلا جناح", "counts": blank(), "sections": {}},
        )
        section = wing["sections"].setdefault(
            entry["section"],
            {
                "grade": entry["grade"],
                "code": entry["code"],
                "counts": blank(),
            },
        )
        for target in (total, wing["counts"], section["counts"]):
            target["total"] += 1
            if entry["attended"]:
                target["present"] += 1
                target["late"] += int(entry["late"])
            else:
                target["absent"] += 1
                target["excused"] += int(not entry["unexcused"])
    for counts in [total, *(w["counts"] for w in wings.values())]:
        counts["pct"] = attendance_rate(counts["present"], counts["total"], empty=None)
    grade_names = dict(ClassGroup.GRADES)
    out_wings = []
    for wing in sorted(wings.values(), key=lambda w: w["name"]):
        sections = sorted(wing["sections"].values(), key=lambda s: (s["grade"], s["code"]))
        for section in sections:
            section["grade_label"] = grade_names.get(section["grade"], section["grade"])
            c = section["counts"]
            c["pct"] = attendance_rate(c["present"], c["total"], empty=None)
        out_wings.append({"name": wing["name"], "counts": wing["counts"], "sections": sections})
    return {"summary": total, "wings": out_wings}


# ═════════════════════════════════════════════════════════════════════
# تحرّكات الطلبة: قيدٌ ونقلٌ وانسحابٌ وتغيير شعبة (W-20261105-009)
# ═════════════════════════════════════════════════════════════════════

#: أنواعُ التحرّك بالترتيب الذي تُعرض به في المرشِّح.
MOVEMENT_KINDS = [
    ("enrol", "قيد"),
    ("transfer_in", "نقل وارد"),
    ("transfer_out", "نقل صادر"),
    ("withdraw", "انسحاب"),
    ("section_change", "تغيير شعبة"),
]
_KIND_LABELS = dict(MOVEMENT_KINDS)


def _class_label(group: Any) -> str:
    return group.short_label if group is not None else "—"


def enrollment_movements(
    school: Any,
    *,
    start: Any = None,
    end: Any = None,
    class_group_id: Any = None,
    kind: str = "",
) -> list[dict[str, Any]]:
    """التحرّكاتُ الزمنيّةُ لطلبة المدرسة كلِّها، الأحدثُ أوّلاً — بلا `request` فتصلح للتصدير.

    لا جدولَ جديداً: القيدُ من `StudentEnrollment`، والنقلُ الوارد والصادر وتغييرُ الشعبة
    (الانتقال الداخلي) من `StudentTransfer` المكتمل، والانسحابُ من مغادرة عضويّة الطالب
    (`Membership.left_at`). والتسجيلُ الذي ينشئه الانتقالُ الداخليُّ نفسُه لا يُعدّ «قيداً» ثانيةً.
    المرشِّحُ بالشعبة يطابق كلَّ تحرّكٍ مسّ الشعبةَ: القيدُ فيها، والتغييرُ منها أو إليها.
    """
    from .models import StudentTransfer

    rows: list[dict[str, Any]] = []

    transfers = list(
        StudentTransfer.objects.filter(school=school, status="completed").select_related(
            "student", "to_class_group"
        )
    )
    # قيدٌ ينشئه الانتقالُ الداخليّ يوم نفاذه: يُستبعد من «القيد» ويُقرأ تغييرَ شعبة.
    internal_keys = {
        (t.student_id, t.to_class_group_id, t.transfer_date)
        for t in transfers
        if t.direction == "internal" and t.to_class_group_id
    }

    enrollments = list(
        StudentEnrollment.objects.filter(class_group__school=school)
        .select_related("student", "class_group")
        .order_by("student_id", "enrolled_at", "id")
    )
    for e in enrollments:
        if (e.student_id, e.class_group_id, e.enrolled_at) in internal_keys:
            continue
        rows.append(
            {
                "kind": "enrol",
                "date": e.enrolled_at,
                "student": e.student,
                "class_ids": {e.class_group_id},
                "detail": f"قيدٌ في الشعبة {_class_label(e.class_group)}",
            }
        )

    # الشعبةُ التي غادرها الطالبُ بالنقل الداخلي: تسجيلٌ أُغلق في اليوم السابق للنقل (internal_transfer).
    left_on = {(e.student_id, e.left_at): e for e in enrollments if e.left_at is not None}
    # آخرُ شعبةٍ للطالب — لإسناد النقل الوارد/الصادر والانسحاب إلى شعبةٍ في مرشِّح الشعبة.
    last_class = {e.student_id: e.class_group for e in enrollments}
    for t in transfers:
        if t.direction == "internal":
            source = left_on.get((t.student_id, t.transfer_date - dt.timedelta(days=1)))
            ids = {t.to_class_group_id} | ({source.class_group_id} if source else set())
            src_label = _class_label(source.class_group if source else None)
            detail = f"من {src_label} إلى {_class_label(t.to_class_group)}"
            row_kind = "section_change"
        else:
            group = last_class.get(t.student_id)
            ids = {group.pk} if group is not None else set()
            detail = t.other_school_name
            row_kind = "transfer_in" if t.direction == "in" else "transfer_out"
        rows.append(
            {
                "kind": row_kind,
                "date": t.transfer_date,
                "student": t.student,
                "class_ids": ids,
                "detail": detail,
            }
        )

    departed = Membership.objects.filter(
        school=school, role__name="student", left_at__isnull=False
    ).select_related("user")
    for m in departed:
        group = last_class.get(m.user_id)
        reason = m.get_departure_reason_display() or "—"
        rows.append(
            {
                "kind": "withdraw",
                "date": m.left_at,
                "student": m.user,
                "class_ids": {group.pk} if group is not None else set(),
                "detail": f"{reason} — {m.departure_reference}"
                if m.departure_reference
                else reason,
            }
        )

    wanted = str(class_group_id) if class_group_id else ""
    out = []
    for r in rows:
        if kind and r["kind"] != kind:
            continue
        if (start is not None and r["date"] < start) or (end is not None and r["date"] > end):
            continue
        if wanted and wanted not in {str(i) for i in r["class_ids"]}:
            continue
        r["kind_label"] = _KIND_LABELS[r["kind"]]
        out.append(r)
    out.sort(key=lambda r: (r["date"], r["student"].full_name), reverse=True)
    return out


def movement_filters(params: Any, school: Any) -> dict[str, Any]:
    """مرشِّحاتُ التحرّكات من معاملات الرابط — تاريخٌ غيرُ صالحٍ يُهمَل، والشعبةُ تُقبل من شعب هذه المدرسة وحدَها."""

    def day(name: str) -> dt.date | None:
        try:
            return dt.date.fromisoformat(params.get(name, ""))
        except ValueError:
            return None

    group_id = params.get("class_group") or None
    try:
        if group_id and not ClassGroup.objects.filter(pk=group_id, school=school).exists():
            group_id = None
    except (ValueError, ValidationError):
        group_id = None
    return {
        "start": day("from"),
        "end": day("to"),
        "class_group_id": group_id,
        "kind": params.get("kind", ""),
    }


def movements_for_params(school: Any, params: Any) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """`(التحرّكات، المرشِّحات)` من معاملات الرابط — للشاشة وللتصدير معاً."""
    filters = movement_filters(params, school)
    return enrollment_movements(school, **filters), filters


def active_classes(school: Any) -> Any:
    """شعبُ المدرسة الفعّالة لقائمة المرشِّح."""
    return ClassGroup.objects.filter(school=school, is_active=True).order_by("grade", "section")

"""قراءاتُ شؤون الطلبة التي يشترك فيها أكثرُ من مسار — بلا `request` فتعمل في العامل كما في الطلب."""

from __future__ import annotations

from typing import Any

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


# ── تحرّكات الطلبة: قيدٌ ونقلٌ وانسحابٌ وتغيير شعبة (W-20261106-016) ──

#: أنواعُ الحركة وتسمياتُها — المصدرُ الواحد للشاشة والتصدير.
MOVEMENT_KINDS = [
    ("enrol", "قيد"),
    ("transfer_in", "نقل وارد"),
    ("transfer_out", "نقل صادر"),
    ("withdrawal", "انسحاب"),
    ("section_change", "تغيير شعبة"),
]


def _movement_class_text(group) -> str:
    from core.labels import class_label

    return class_label(group.grade, group.section) if group is not None else ""


def _movement_events(rows, transfers) -> list[dict[str, Any]]:
    """يشتقّ الحركاتِ من قيود العام وانتقالاته المكتملة — لا جدولَ حركاتٍ ثانياً."""
    labels = dict(MOVEMENT_KINDS)
    transferred_in = {t.student_id for t in transfers if t.direction == "in"}
    transferred_out = {t.student_id for t in transfers if t.direction == "out"}
    by_student: dict[Any, list] = {}
    for row in rows:
        by_student.setdefault(row.student_id, []).append(row)

    events: list[dict[str, Any]] = []

    def add(kind, day, student, to_group=None, from_group=None, detail=""):
        events.append(
            {
                "kind": kind,
                "kind_label": labels[kind],
                "date": day,
                "student": student,
                "class_group_ids": {str(g.id) for g in (to_group, from_group) if g is not None},
                "class_text": _movement_class_text(to_group),
                "from_text": _movement_class_text(from_group),
                "detail": detail,
            }
        )

    for student_id, mine in by_student.items():
        first, last = mine[0], mine[-1]
        # قيدٌ جديد: لا قيدَ سابقٌ للطالب في المدرسة؛ والوارد يُعرض نقلاً لا قيداً.
        if not first.had_earlier and student_id not in transferred_in:
            add("enrol", first.enrolled_at, first.student, first.class_group)
        for prev, nxt in zip(mine, mine[1:], strict=False):
            if prev.class_group_id != nxt.class_group_id:
                add(
                    "section_change",
                    nxt.enrolled_at,
                    nxt.student,
                    nxt.class_group,
                    prev.class_group,
                )
        # انسحاب: لا قيدَ نشطاً في العام وآخرُ قيدٍ أُغلق بتاريخ؛ والمنقولُ صادراً يُعرض نقلاً.
        closed = not any(r.is_active for r in mine)
        if closed and last.left_at and student_id not in transferred_out:
            add("withdrawal", last.left_at, last.student, from_group=last.class_group)

    for t in transfers:
        if t.direction not in ("in", "out"):
            continue
        mine = by_student.get(t.student_id)
        group = mine[-1].class_group if mine else None
        incoming = t.direction == "in"
        add(
            "transfer_in" if incoming else "transfer_out",
            t.transfer_date,
            t.student,
            group if incoming else None,
            None if incoming else group,
            t.other_school_name,
        )
    return events


def enrolment_movements(
    school,
    year: str,
    *,
    class_group_id: str = "",
    date_from=None,
    date_to=None,
    kind: str = "",
) -> list[dict[str, Any]]:
    """قائمةُ تحرّكات الطلبة الزمنيّة بنطاق المدرسة والعام، الأحدثُ أوّلاً.

    تُشتقّ من `StudentEnrollment` (القيدُ وتغييرُ الشعبة والانسحاب) ومن `StudentTransfer`
    المكتمل (الوارد والصادر). الشعبةُ تُطابق شعبةَ الحركة أو الشعبةَ التي غادرها الطالب.
    """
    from student_affairs.models import StudentTransfer

    earlier = StudentEnrollment.objects.filter(
        student=OuterRef("student"),
        class_group__school=school,
        enrolled_at__lt=OuterRef("enrolled_at"),
    )
    rows = list(
        StudentEnrollment.objects.filter(
            class_group__school=school, class_group__academic_year=year
        )
        .annotate(had_earlier=Exists(earlier))
        .select_related("student", "class_group")
        .order_by("student_id", "enrolled_at", "id")
    )
    transfers = list(
        StudentTransfer.objects.filter(school=school, academic_year=year, status="completed")
        .select_related("student")
        .order_by("transfer_date")
    )
    events = _movement_events(rows, transfers)

    if kind:
        events = [e for e in events if e["kind"] == kind]
    if class_group_id:
        events = [e for e in events if str(class_group_id) in e["class_group_ids"]]
    if date_from:
        events = [e for e in events if e["date"] >= date_from]
    if date_to:
        events = [e for e in events if e["date"] <= date_to]
    events.sort(key=lambda e: (e["date"], e["student"].full_name), reverse=True)
    return events


def year_sections(school, year: str) -> list[tuple[str, str]]:
    """شعبُ المدرسة في العام `(المعرّف، التسمية)` بترتيب المدرسة — لقائمة ترشيح التحرّكات."""
    from core.labels import class_label

    groups = ClassGroup.objects.filter(school=school, academic_year=year).in_school_order()
    return [(str(g.id), class_label(g.grade, g.section)) for g in groups]


def movement_filters(params: Any) -> dict[str, Any]:
    """مرشِّحاتُ التحرّكات من `QueryDict` — للشاشة والتصدير معاً فيطابق الملفُّ ما تعرضه الشاشة."""
    from datetime import date

    def day(value: str | None):
        try:
            return date.fromisoformat(value or "")
        except ValueError:
            return None

    return {
        "class_group_id": params.get("section", ""),
        "date_from": day(params.get("from")),
        "date_to": day(params.get("to")),
        "kind": params.get("kind", ""),
    }

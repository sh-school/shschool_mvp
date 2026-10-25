"""خدمةُ طلب الالتحاق (نموذج 07، المرحلة 1): التسجيلُ ثمّ سلسلةُ التدقيق والاعتماد والتشعيب والإدخال (W-20261001-033).

تُعيد استعمالَ قواعد `transfer_chain` (مستنداتُه الأحد عشر ومراحلُه) كما هي، ولا تلمس `StudentTransfer`.
الرقمُ الشخصيّ والحالةُ الصحّيّة لا تدخل سجلّاً ولا رسالةً هنا: التدقيقُ يحمل معرّفَ الطلب ونوعَ الإجراء فقط.
"""

from django.db import transaction
from django.utils import timezone

from .admission_models import AdmissionApplication
from .transfer_chain import _check_rules, _stamp

#: حقولُ الطلب القادمة من النموذج، ما عدا المنفّذ والمراحل.
APPLICATION_FIELDS = (
    "student_name",
    "student_national_id",
    "nationality",
    "current_school",
    "grade",
    "health_status",
    "living_with",
    "transport",
    "housing_area",
    "housing_street",
    "housing_house",
    "applicant_name",
    "applicant_national_id",
    "applicant_relationship",
    "applicant_phone",
    "declaration_accepted",
)


def create_application(school, data: dict, actor, academic_year: str) -> AdmissionApplication:
    """يسجّل طلبَ التحاقٍ قيد الانتظار بلا حسابٍ للطالب؛ الإقرارُ شرطٌ لا يُتجاوز."""
    if not data.get("declaration_accepted"):
        raise ValueError("لا يُسجَّل الطلب قبل إقرار مقدِّمه.")
    values = {k: data[k] for k in APPLICATION_FIELDS if k in data}
    if "birth_date" in data:  # مفتاحُ النموذج؛ والحقلُ date_of_birth كما في Profile
        values["date_of_birth"] = data["birth_date"]
    return AdmissionApplication.objects.create(
        school=school,
        academic_year=academic_year,
        created_by=actor,
        updated_by=actor,
        **values,
    )


def _enter_into_system(application, school, class_group, gender: str):
    """ينشئ حسابَ الطالب في النظام الداخليّ ويربطه بالطلب (مرحلةُ الإدخال)."""
    from .services import StudentService

    if not application.student_national_id:
        raise ValueError("لا إدخالَ بلا الرقم الشخصي للطالب.")
    student = StudentService.create_student(
        school,
        {
            "national_id": application.student_national_id,
            "full_name": application.student_name,
            "gender": gender,
            "birth_date": application.date_of_birth,
            "nationality": application.nationality,
            "class_group_id": class_group.pk,
        },
    )
    application.linked_student = student
    return student


@transaction.atomic
def apply_action(
    application,
    action: str,
    notes: str,
    actor,
    documents=None,
    missing_reason: str = "",
    class_group=None,
    gender: str = "",
):
    """يطبّق إجراءً من السلسلة على الطلب أو يرفع ValueError قبل أيّ كتابة.

    يعيد حسابَ الطالب المنشأ عند «enter» وإلا None. التشعيبُ يحتاج شعبةً من مدرسة الطلب وبصفّه المطلوب.
    """
    locked = AdmissionApplication.objects.select_for_update().get(pk=application.pk)
    for field in (
        "status",
        "reviewed_at",
        "approved_at",
        "placed_at",
        "entered_at",
        "documents_checked",
        "to_class_group_id",
    ):
        setattr(application, field, getattr(locked, field))
    documents = list(documents or [])
    _check_rules(application, action, notes, documents, missing_reason)

    now = timezone.now()
    fields = ["status", "notes", "updated_by", "updated_at"]
    created = None
    if action == "review":
        application.documents_checked = sorted(set(documents), key=int)
        application.documents_missing_reason = (missing_reason or "").strip()[:500]
        _stamp(application, "reviewed", actor, now)
        fields += ["documents_checked", "documents_missing_reason", "reviewed_by", "reviewed_at"]
    elif action == "approved":
        _stamp(application, "approved", actor, now)
        application.status = "approved"
        fields += ["approved_by", "approved_at"]
    elif action == "place":
        if class_group is None or class_group.school_id != application.school_id:
            raise ValueError("اختر شعبةً من مدرسة الطلب.")
        if class_group.grade != application.grade:
            raise ValueError("الشعبةُ يجب أن تكون من الصف المطلوب.")
        application.to_class_group = class_group
        _stamp(application, "placed", actor, now)
        fields += ["to_class_group", "placed_by", "placed_at"]
    elif action == "enter":
        created = _enter_into_system(
            application, application.school, application.to_class_group, gender
        )
        _stamp(application, "entered", actor, now)
        fields += ["linked_student", "entered_by", "entered_at"]
    else:  # rejected / completed / cancelled
        application.status = action
    if notes:
        separator = "\n---\n" if application.notes else ""
        application.notes += f"{separator}[{actor.full_name}]: {notes}"
    application.updated_by = actor
    application.save(update_fields=fields)
    return created

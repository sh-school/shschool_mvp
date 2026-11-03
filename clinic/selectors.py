"""
clinic/selectors.py — قراءاتُ العيادة (W-20261020-030، W-20261102-001)
═══════════════════════════════════════════════════════════════════════
اختيارُ الطالب في الزيارة بثلاثة مداخل: اسمٌ مطبَّع ببداية الكلمة، صفٌّ ثمّ شعبة، رقمُ الطالب.
كلُّها تخرج بشكلٍ واحد (`StudentChoice`) وباستعلامين لا أكثر: الطلبةُ (مع الملفّ الشخصيّ وعلامةِ
المراعاة بـ`Exists`) ثمّ قيودُهم النشطة. والنتيجةُ لا تحمل إلا الاسمَ والشعبةَ وسنةَ الميلاد وعلامةً
محايدة — لا رقمَ وطنيّاً ولا تاريخَ ميلادٍ كاملاً ولا شيئاً صحّيّاً.
"""

from __future__ import annotations

import datetime
import re
from dataclasses import dataclass
from functools import reduce
from operator import and_

from django.core.exceptions import ValidationError
from django.db.models import Exists, OuterRef, Prefetch, Q, Value
from django.db.models.functions import Lower, Replace

from core.academic_calendar import academic_year_for_school

#: أقصى نتائج القائمة — قائمةٌ قصيرةٌ تُلمس لا جدولٌ يُمرَّر.
MAX_RESULTS = 12
#: أقلُّ حروفٍ للبحث بالاسم.
MIN_QUERY = 2
#: نافذةُ «زوّار الأيام الأخيرة».
RECENT_DAYS = 7

_ARABIC_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹", "01234567890123456789")
#: أشكالٌ تُوحَّد قبل المقارنة: الهمزاتُ على الألف، والتاءُ المربوطة هاءً، والألفُ المقصورة ياءً.
_FOLD = (
    ("أ", "ا"),
    ("إ", "ا"),
    ("آ", "ا"),
    ("ٱ", "ا"),
    ("ة", "ه"),
    ("ى", "ي"),
    ("ؤ", "و"),
    ("ئ", "ي"),
    ("ـ", ""),
)
_TASHKEEL = re.compile("[ً-ٰٟ]")
_SPACES = re.compile(r"\s+")


def normalize_ar(text: str) -> str:
    """يوحّد الهمزاتِ والتاءَ والياءَ ويحذف التشكيلَ والتطويل — ويطابق `_normalized_name()` في القاعدة."""
    out = _TASHKEEL.sub("", (text or "").translate(_ARABIC_DIGITS))
    for src, dst in _FOLD:
        out = out.replace(src, dst)
    return _SPACES.sub(" ", out).strip().lower()


def _normalized_name():
    expr = Lower("full_name")
    for src, dst in _FOLD:
        expr = Replace(expr, Value(src), Value(dst))
    return expr


@dataclass(frozen=True)
class StudentChoice:
    id: str
    full_name: str
    class_label: str  # «9/1» أو فارغ
    birth_year: int | None
    needs_care: bool
    similar: bool = False  # في القائمة من يشاركه الاسمَ نفسَه بعد التطبيع


def _enrollment_prefetch():
    from core.models import StudentEnrollment

    return Prefetch(
        "enrollments",
        queryset=StudentEnrollment.objects.filter(is_active=True)
        .select_related("class_group")
        .newest_first(),
        to_attr="active_enrollments",
    )


def _class_label(user) -> str:
    enrollments = getattr(user, "active_enrollments", None) or []
    if not enrollments:
        return ""
    cg = enrollments[0].class_group
    return f"{cg.grade[1:]}/{cg.section}"


def _birth_year(user) -> int | None:
    profile = getattr(user, "profile", None)
    born = profile.date_of_birth if profile is not None else None
    return born.year if born else None


def _to_choices(users) -> list[StudentChoice]:
    names: dict[str, int] = {}
    for u in users:
        key = normalize_ar(u.full_name)
        names[key] = names.get(key, 0) + 1
    return [
        StudentChoice(
            id=str(u.id),
            full_name=u.full_name,
            class_label=_class_label(u),
            birth_year=_birth_year(u),
            needs_care=bool(u.needs_care_flag),
            similar=names[normalize_ar(u.full_name)] > 1,
        )
        for u in users
    ]


def _students(school):
    """طلبةُ المدرسة النشطون — أساسُ المداخل الثلاثة (استعلامٌ واحدٌ بعدّه prefetch)."""
    from clinic.models import HealthRecord
    from core.models import CustomUser

    return (
        CustomUser.objects.filter(
            memberships__school=school,
            memberships__role__name="student",
            memberships__is_active=True,
        )
        .distinct()
        .select_related("profile")
        .annotate(
            needs_care_flag=Exists(
                HealthRecord.objects.filter(student=OuterRef("pk"), needs_care=True)
            )
        )
        .prefetch_related(_enrollment_prefetch())
    )


def search_students(
    school, term: str, limit: int = MAX_RESULTS, *, user=None
) -> list[StudentChoice]:
    """بحثٌ بالاسم (كلُّ كلمةٍ مُدخَلة بدايةُ كلمةٍ في الاسم بعد التطبيع) أو برقم الطالب."""
    text = (term or "").strip()
    digits = _SPACES.sub("", text.translate(_ARABIC_DIGITS))
    if digits.isdigit():
        from core.privacy import national_id_search_q

        qs = _students(school).filter(national_id_search_q("national_id", digits, user=user))
        return _to_choices(list(qs.order_by("full_name")[:limit]))
    tokens = [t for t in normalize_ar(text).split(" ") if t]
    if sum(len(t) for t in tokens) < MIN_QUERY:
        return []
    cond = reduce(
        and_, (Q(norm_name__startswith=t) | Q(norm_name__contains=f" {t}") for t in tokens)
    )
    qs = _students(school).annotate(norm_name=_normalized_name()).filter(cond)
    return _to_choices(list(qs.order_by("full_name")[:limit]))


def students_of_class(school, grade: str, section: str, limit: int = 60) -> list[StudentChoice]:
    """طلبةُ شعبةٍ بعينها — بعد اختيار الصفّ فالشعبة. السقفُ أكبرُ من الاسم لأنّ الشعبةَ محدودة."""
    qs = _students(school).filter(
        enrollments__is_active=True,
        enrollments__class_group__school=school,
        enrollments__class_group__grade=grade,
        enrollments__class_group__section=section,
        enrollments__class_group__academic_year=academic_year_for_school(school),
    )
    return _to_choices(list(qs.order_by("full_name")[:limit]))


def class_options(school) -> list[tuple[str, str, list[str]]]:
    """(رمزُ الصفّ، اسمُه، شُعبُه) بترتيب المدرسة — استعلامٌ واحد."""
    from core.models import ClassGroup

    out: dict[str, set[str]] = {}
    for grade, section in ClassGroup.objects.filter(
        school=school, is_active=True, academic_year=academic_year_for_school(school)
    ).values_list("grade", "section"):
        out.setdefault(grade, set()).add(section)
    return [(g, label, sorted(out[g])) for g, label in ClassGroup.GRADES if g in out]


def recent_visitors(school, day: datetime.date, limit: int = MAX_RESULTS) -> list[StudentChoice]:
    """طلبةٌ زاروا العيادة في آخر `RECENT_DAYS` يوماً حتى `day` — الأحدثُ أوّلاً."""
    from clinic.models import ClinicVisit

    since = day - datetime.timedelta(days=RECENT_DAYS)
    ids = list(
        ClinicVisit.objects.filter(school=school, visit_date__date__range=(since, day))
        .order_by("-visit_date")
        .values_list("student_id", flat=True)[: limit * 4]
    )
    ordered = list(dict.fromkeys(ids))[:limit]
    if not ordered:
        return []
    users = {u.pk: u for u in _students(school).filter(pk__in=ordered)}
    return _to_choices([users[i] for i in ordered if i in users])


def student_choice(school, student_id) -> StudentChoice | None:
    """طالبٌ واحدٌ من المدرسة بمعرّفه — أو `None` (معرّفٌ غيرُ صالحٍ أو من مدرسةٍ أخرى)."""
    try:
        users = list(_students(school).filter(pk=student_id))
    except (ValueError, ValidationError):
        return None
    return _to_choices(users)[0] if users else None

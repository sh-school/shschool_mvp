"""
wings/scope.py — نطاقُ الطلبة الذين يصل إليهم المستخدم: جناحُه، أو المدرسةُ كما كانت.

قرارا المستخدم 2026-09-14 و2026-09-15: «المشرفُ لجناحه فقط» في كلّ ما يقرأ فيه عن الطلبة —
مركزُ معلومات الطلبة، وشؤونُ الطلبة، والسلوكُ، وتقريرُ الغياب، والكنترول. **ولا يُسأل هذا
السؤالُ في شاشةٍ بعينها**: كلُّ شاشةٍ تأخذ `student_scope_for(request)` وتمرّ استعلاماتُها على
`narrow` قبل المرشِّحات والعدّ والترقيم، وكلُّ معرّفٍ يأتي من الرابط أو النموذج يمرّ على
`require_student` / `require_class` فيعود 404 لما خرج عن الجناح.

## من يُقيَّد

الأدوارُ في `WING_BOUND_ROLES` بالدور **الخامّ** (`user.get_role()`) لا الموسَّع: `ROLE_INHERITS`
يجعل النائبَ الإداريّ وارثاً للمشرف، ولو قُورن الموسَّعُ لقُيِّد النائبُ بجناحٍ لا يحمله. وكلُّ من
عداهم — القيادةُ والأخصائيّون والمنسّقون والمعلّمون — نطاقُهم `None`: تبقى قواعدُ شاشاتهم كما
كانت حرفاً، ولا يُنفَّذ لهم استعلامٌ واحدٌ زائد.

## الطالبُ في جناحٍ واحد — بقيده الجاري

«في أيّ شعبةٍ هذا الطالب؟» جوابُه **أحدثُ قيدٍ نشطٍ في العام الجاري**، لا كلُّ قيوده: القيدُ
الفريدُ في القاعدة على الزوج (طالب، شعبة)، فمئاتُ الطلبة يحملون قيدين نشطين. ولو عُدّ كلُّ قيدٍ
لرأى مشرفا جناحين الطالبَ نفسَه. والجناحُ الذي يُحمل اليوم أصيلاً أو بديلاً (`wings_of`) — فمشرفٌ
غُطّي جناحُه ببديلٍ ساري التغطية نطاقُه فارغٌ مدّتَها.

## ما يُحجب عن المقيَّد وإن كان الطالبُ في جناحه (قرارُ 2026-09-15)

- الدرجاتُ ونتائجُ الموادّ — التحصيلُ ليس من مهامّه في الدليل (`hides_grades`).
- ملاحظاتُ الأخصائيّ الاجتماعيّ والنفسيّ (`hides_specialist_notes`).
- من العيادة يرى تاريخَ الزيارة و«أُعيد إلى المنزل» فقط، لا السببَ ولا فصيلةَ الدم
  (`clinic_summary_only`).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from django.db.models import QuerySet
from django.http import Http404, HttpRequest

from core.models import ClassGroup, CustomUser, School, StudentEnrollment
from core.permissions import WING_BOUND_ROLES

#: خاناتُ مركز المعلومات التي لا يقرؤها المقيَّدُ بجناحه.
SPECIALIST_CATEGORIES = frozenset({"social_worker", "psychologist"})


@dataclass(frozen=True)
class StudentScope:
    """نطاقُ مستخدمٍ في مدرسة — `wing_ids is None` يعني «بلا قيدِ جناح»."""

    school: School
    wing_ids: frozenset[Any] | None
    year: str | None = None
    _cache: dict[str, Any] = field(default_factory=dict, compare=False, repr=False)

    # ── السؤال ─────────────────────────────────────────────────────────
    @property
    def is_wing_bound(self) -> bool:
        return self.wing_ids is not None

    @property
    def hides_grades(self) -> bool:
        return self.is_wing_bound

    @property
    def hides_specialist_notes(self) -> bool:
        return self.is_wing_bound

    @property
    def clinic_summary_only(self) -> bool:
        return self.is_wing_bound

    # ── الشُّعبُ والطلبة ─────────────────────────────────────────────────
    def class_groups(self) -> QuerySet[ClassGroup]:
        """شُعبُ الجناح النشطةُ في العام الجاري — وللمقيَّد وحدَه."""
        assert self.is_wing_bound, "class_groups() للمقيَّد بجناحه — غيرُه لا يُضيَّق"
        groups: QuerySet[ClassGroup] = ClassGroup.objects.filter(
            school=self.school,
            academic_year=self.year,
            is_active=True,
            wing_id__in=self.wing_ids or (),
        )
        return groups

    def student_ids(self) -> frozenset[Any]:
        """طلبةُ الجناح: من كان **قيدُه الجاري** في شعبةٍ من شُعبه. يُحسب مرّةً للطلب."""
        assert self.is_wing_bound, "student_ids() للمقيَّد بجناحه — غيرُه لا يُضيَّق"
        if "students" not in self._cache:
            if not self.wing_ids:
                self._cache["students"] = frozenset()
            else:
                rows = (
                    StudentEnrollment.objects.filter(
                        is_active=True,
                        class_group__school=self.school,
                        class_group__academic_year=self.year,
                    )
                    .order_by("student_id", "-enrolled_at", "-id")
                    .values_list("student_id", "class_group__wing_id")
                )
                current: dict[Any, Any] = {}
                for student_id, wing_id in rows:
                    current.setdefault(student_id, wing_id)
                self._cache["students"] = frozenset(
                    sid for sid, wing_id in current.items() if wing_id in self.wing_ids
                )
        students: frozenset[Any] = self._cache["students"]
        return students

    # ── التضييق ─────────────────────────────────────────────────────────
    def narrow(self, qs: QuerySet[Any], student_path: str = "student_id") -> QuerySet[Any]:
        """يضيّق استعلاماً بطلبة الجناح — وغيرُ المقيَّد يُعاد له استعلامُه كما هو.

        `student_path` مسارُ معرّف الطالب في الاستعلام: `student_id` للحضور والمخالفات،
        و`pk` لـ`CustomUser`، و`user_id` للعضويّة، و`student__pk` وما شابه.
        """
        if not self.is_wing_bound:
            return qs
        return qs.filter(**{f"{student_path}__in": self.student_ids()})

    def narrow_classes(self, qs: QuerySet[Any], class_path: str = "class_group") -> QuerySet[Any]:
        """يضيّق استعلاماً بشُعب الجناح (لقوائم الشُّعب وحصصها)."""
        if not self.is_wing_bound:
            return qs
        return qs.filter(**{f"{class_path}__in": self.class_groups()})

    def covers_student(self, student_id: Any) -> bool:
        if not self.is_wing_bound:
            return True
        return _as_key(student_id) in {_as_key(s) for s in self.student_ids()}

    def covers_class(self, class_id: Any) -> bool:
        if not self.is_wing_bound:
            return True
        return self.class_groups().filter(pk=class_id).exists()

    def require_student(self, student_id: Any) -> None:
        """404 لطالبٍ خارج الجناح — وجودُه في جناحٍ غيره ليس شأنَ المشرف."""
        if not self.covers_student(student_id):
            raise Http404("ليس من طلبة جناحك")

    def require_class(self, class_id: Any) -> None:
        if not self.covers_class(class_id):
            raise Http404("ليست من شُعب جناحك")

    def year_for(self, requested: str | None, fallback: str) -> str:
        """العامُ المعروض: المقيَّدُ على العام الجاري دائماً — `?year=` لا يوسّع نطاقَه."""
        if self.is_wing_bound:
            return self.year or fallback
        return requested or fallback


def _as_key(value: Any) -> str:
    return str(value)


def student_scope(user: CustomUser, school: School) -> StudentScope:
    """نطاقُ المستخدم في المدرسة. غيرُ المقيَّد بلا أيّ استعلام."""
    if getattr(user, "is_superuser", False) or user.get_role() not in WING_BOUND_ROLES:
        return StudentScope(school, None)
    from core.academic_calendar import academic_year_for_school
    from wings.services import wings_of

    year = academic_year_for_school(school)  # type: ignore[no-untyped-call]
    wings = wings_of(user, school, year)
    return StudentScope(school, frozenset(w.id for w in wings), year)


def student_scope_for(request: HttpRequest) -> StudentScope:
    """نطاقُ صاحب الطلب — يُحسب مرّةً ويُحفظ على الطلب."""
    cached = getattr(request, "_student_scope", None)
    if cached is not None:
        scope: StudentScope = cached
        return scope
    user: Any = request.user
    school = getattr(request, "school", None) or user.get_school()
    scope = student_scope(user, school)
    request._student_scope = scope  # type: ignore[attr-defined]
    return scope

"""من يحمل الجناحَ في يوم — منطقُ الحمل لـ`Wing` (إنابةٌ ثمّ تعيينٌ ثمّ الأصيلُ القديم).

مفصولٌ عن `academic.py` لسقف حجم الملفّ؛ و`Wing` يرثه فتبقى الدوالُّ على الجناح كما عُرفت
(`current_supervisor` و`is_held_by`) ويُضاف إليها `holders` و`is_assigned` (W-20261119-001).
"""

import datetime
from typing import Any, NamedTuple

from django.db.models import Q
from django.utils import timezone

from .user import CustomUser

#: دورا الجناح في سجلّ التعيينات والإنابة.
WING_SUPERVISOR = "wing_supervisor"
FIELD_SUPERVISOR = "field_supervisor"
WING_ROLES = [(WING_SUPERVISOR, "مشرف الجناح"), (FIELD_SUPERVISOR, "المشرف الميداني")]


class WingHolders(NamedTuple):
    """من يحمل الجناحَ في يومٍ: مشرفُه الإداريّ ومشرفُه الميدانيّ."""

    supervisor: CustomUser | None
    field: CustomUser | None


class WingHoldersMixin:
    """دوالُّ الحمل — تقرأ `coverages` و`assignments` و`supervisor` من `Wing`."""

    coverages: Any
    assignments: Any
    supervisor: Any
    objects: Any

    def active_coverage(
        self, on_date: datetime.date | None = None, role: str = WING_SUPERVISOR
    ) -> Any:
        """التغطيةُ الساريةُ في هذا اليوم لهذا الدور — أو `None`.

        والأحدثُ بدايةً يغلب عند التساوي: قيدُ الاستبعاد يمنع التداخلَ في
        القاعدة، لكنّ قراءةً بلا ترتيبٍ تُرجع ما تُرجعه القاعدةُ أوّلاً.
        """
        day = on_date or timezone.localdate()
        # بالتصفية في الذاكرة على `.all()` لتُقرأ من الجلب المسبق إن وُجد (لوحةُ الأجنحة تعرض خمسةً معاً).
        live = [c for c in self.coverages.all() if c.role == role and c.covers(day)]
        return max(live, key=lambda c: c.start_date, default=None)

    def assignment_on(self, role: str, on_date: datetime.date | None = None) -> Any:
        """التعيينُ الساري لهذا الدور في هذا اليوم — أو `None`."""
        day = on_date or timezone.localdate()
        live = [a for a in self.assignments.all() if a.role == role and a.covers(day)]
        return max(live, key=lambda a: a.start_date, default=None)

    def holder_of(self, role: str, on_date: datetime.date | None = None) -> CustomUser | None:
        """حاملُ هذا الدور في هذا اليوم: الإنابةُ فوق التعيين، ثمّ `Wing.supervisor` لما قبل التعيينات.

        والرجوعُ إلى `supervisor` لدور المشرف وحدَه ولما قبل أوّل تعيينٍ مسجَّلٍ فقط: بعد
        بدء السجلّ الزمنيّ يكون فراغُه فراغاً حقيقيّاً لا يُملأ بحقلٍ قديم.
        """
        day = on_date or timezone.localdate()
        cover = self.active_coverage(day, role)
        if cover:
            holder: CustomUser = cover.substitute
            return holder
        assigned = self.assignment_on(role, day)
        if assigned:
            holder = assigned.user
            return holder
        if role != WING_SUPERVISOR:
            return None
        starts = [a.start_date for a in self.assignments.all() if a.role == role]
        legacy: CustomUser | None = self.supervisor if not starts or day < min(starts) else None
        return legacy

    def current_supervisor(self, on_date: datetime.date | None = None) -> CustomUser | None:
        """من يحمل الجناحَ في هذا اليوم — الإنابةُ ثمّ التعيينُ ثمّ الأصيلُ القديم.

        **كلُّ صلاحيّةٍ واستعلامٍ يمرّ على هذه**، لا على `supervisor`. فالأصيلُ
        حقيقةُ سجلٍّ والحاملُ حقيقةُ يوم: مشرفٌ في إجازةٍ أسبوعاً يبقى أصيلَ
        جناحه، ومن يقرأ ملفّات طلابه في ذلك الأسبوع غيرُه. ومن قرأ `supervisor`
        مباشرةً منح الغائبَ ومنع الحاضر.
        """
        return self.holder_of(WING_SUPERVISOR, on_date)

    def holders(self, on_date: datetime.date | None = None) -> WingHolders:
        """حاملا الجناح في هذا اليوم: مشرفُه والميدانيّ (أيٌّ منهما `None` إن فرغ)."""
        day = on_date or timezone.localdate()
        return WingHolders(
            supervisor=self.holder_of(WING_SUPERVISOR, day),
            field=self.holder_of(FIELD_SUPERVISOR, day),
        )

    @classmethod
    def is_held_by(cls, user: Any, on_date: datetime.date | None = None) -> bool:
        """أيحمل هذا المستخدمُ جناحاً نشطاً في هذا اليوم — معيَّناً أو بديلاً أو أصيلاً قديماً؟

        البديلُ قد يكون ملاحظَ طلبةٍ أو عاملَ خدمات (قرارُ المدير، `SUBSTITUTE_ROLES`)،
        ودورُه لا يفتح الرصد. فالتكليفُ نفسُه هو الإذن — ما دام سارياً.
        وبالسؤال نفسِه الذي يسأله `current_supervisor`: المعيَّنُ والبديلُ الساريان
        يحملان الجناح، والأصيلُ القديمُ يحمله ما لم يُغطَّ أو يبدأ سجلُّ التعيينات.
        """
        from .academic import WingCoverage
        from .wing_assignment import WingAssignment

        if user is None or not getattr(user, "is_authenticated", False):
            return False
        day = on_date or timezone.localdate()
        live = Q(start_date__lte=day) & (Q(end_date__isnull=True) | Q(end_date__gte=day))
        covering = WingCoverage.objects.filter(live, wing__is_active=True)
        started = WingAssignment.objects.filter(role=WING_SUPERVISOR, start_date__lte=day)
        assigned = Q(id__in=WingAssignment.objects.filter(live, user=user).values("wing_id"))
        substitute = Q(id__in=covering.filter(substitute=user).values("wing_id"))
        legacy = (
            Q(supervisor=user)
            & ~Q(id__in=covering.filter(role=WING_SUPERVISOR).values("wing_id"))
            & ~Q(id__in=started.values("wing_id"))
        )
        # استعلامٌ واحدٌ لا ثلاثة: تُستدعى في بوّابات القدرات لكلّ طلب.
        return bool(
            cls.objects.filter(is_active=True).filter(assigned | substitute | legacy).exists()
        )

    @classmethod
    def is_assigned(cls, user: Any, on_date: datetime.date | None = None) -> bool:
        """أمعيَّنٌ هذا المستخدمُ بسجلّ التعيينات (مشرفاً أو ميدانيّاً) في هذا اليوم؟

        الصلاحيةُ بالتعيين لا بالدور: يفتح لوحةَ التحركات وتغييرَ الوجهة لجناحه،
        ولا يصوّت في لجنة السلوك (تبقى بالدور).
        """
        from .wing_assignment import WingAssignment

        if user is None or not getattr(user, "is_authenticated", False):
            return False
        # غيرُ المؤهَّلين بالدور لا يُعيَّنون أصلاً: فلا استعلامَ لمعلّمٍ أو مديرٍ في كلّ طلب.
        if user.get_role() not in WingAssignment.ELIGIBLE_ROLES:
            return False
        day = on_date or timezone.localdate()
        return (
            WingAssignment.objects.filter(user=user, wing__is_active=True, start_date__lte=day)
            .filter(Q(end_date__isnull=True) | Q(end_date__gte=day))
            .exists()
        )

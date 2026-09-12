"""ما تعرضه شاشةُ الأجنحة — مبنيّاً مرّةً واحدةً بعددِ استعلاماتٍ ثابت.

الشاشةُ تعرض خمسةَ أجنحةٍ في طابقين، ولكلٍّ شُعبُه وطلابُه وجرسُه وموضعُه من
الساعة. وقراءةُ ذلك من النماذج مباشرةً تُنتج استعلاماً لكلّ جناحٍ لكلّ سؤال —
عشرين استعلاماً لصفحةٍ واحدة، تزيد بزيادة الأجنحة.

فالعدُّ هنا ثابتٌ لا يتبع عددَ الأجنحة: استعلامان للأجنحة وشُعبها، وواحدٌ
لأعداد الطلاب، وواحدٌ لأجراس اليوم — والباقي قسمةٌ في الذاكرة.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass

from django.db.models import Count, Prefetch, Q
from django.utils import timezone

from core.models import ClassGroup, CustomUser, Membership, StudentEnrollment, Wing, WingCoverage
from core.models.academic import FLOORS, bands_of
from operations.bells import REGULAR, THURSDAY, Bell, Position, bells_for, day_type_for
from operations.day_attendance import confirmations_of, enrolled_of, slots_of


@dataclass(frozen=True)
class WingCard:
    """جناحٌ كما يُقرأ في الشاشة."""

    wing: Wing
    sections: list[ClassGroup]
    student_count: int
    #: من يحمل الجناحَ اليوم — بديلٌ إن غُطّي، وإلّا الأصيل.
    holder: object
    coverage: object
    #: أجراسُ الجناح كما هي — لا كما ترنّ اليوم.
    bands: list
    bells: list[Bell]
    positions: list[Position]
    off_floor: list

    @property
    def is_split(self) -> bool:
        """من الأجراس لا من `bells`: يومَ الجمعة لا جرسَ يرنّ، والجناحُ يبقى
        ذا جرسين. وشارةٌ تختفي في العطلة تُعلّم القارئَ أنّها حالةُ يومٍ لا
        صفةُ ممرّ."""
        return len(self.bands) > 1

    @property
    def levels(self) -> set:
        return {klass.level_type for klass in self.sections}


@dataclass(frozen=True)
class FloorPanel:
    """طابقٌ بأجراسه وأجنحته — والأوّلُ منهما بجرسين."""

    code: str
    label: str
    bells: list[Bell]
    wings: list[WingCard]

    @property
    def student_count(self) -> int:
        return sum(card.student_count for card in self.wings)

    @property
    def section_count(self) -> int:
        return sum(len(card.sections) for card in self.wings)


@dataclass(frozen=True)
class BellTable:
    """جدولُ يومٍ واحد: عمودٌ لكلّ جرسٍ وصفٌّ لكلّ خانة.

    والصفوفُ بالموضع لا بالاسم: «الرابعة» في الأرضيّ رابعةُ الخانات الخامسة،
    وفي الأوّل الرابعة. فكلُّ خليّةٍ تحمل اسمَها ووقتَها معاً، ويُقرأ العمودان
    متجاورين دون ادّعاء أنّ ما تحاذى تطابَق.
    """

    day_type: str
    label: str
    bells: list[Bell]

    @property
    def rows(self) -> list[list]:
        depth = max((len(bell.slots) for bell in self.bells), default=0)
        return [
            [bell.slots[index] if index < len(bell.slots) else None for bell in self.bells]
            for index in range(depth)
        ]


@dataclass(frozen=True)
class Outside:
    """ما هو خارجَ الأجنحة — يُعدّ ويُعرض ولا يُطرح صامتاً.

    شُعبُ التربية الخاصّة الثلاث خارجَ الأجنحة بقرار الإدارة، فمجموعُ طلاب
    الأجنحة أقلُّ من سجلّ المدرسة. وشاشةٌ تقول «الطلاب 731» لمدرسةٍ سجلُّها
    735 لا تكذب في الرقم بل في اسمه — والقارئُ يذهب يبحث عن أربعةٍ لم
    يضيعوا. فيُسمّى المعدودُ بما هو، ويُذكر الباقي بعدده.
    """

    sections: list[ClassGroup]
    student_count: int

    @property
    def section_count(self) -> int:
        return len(self.sections)


def outside_the_wings(school, year: str) -> Outside:
    """الشُّعبُ النشطةُ بلا جناحٍ وطلابُها."""
    sections = list(
        ClassGroup.objects.filter(school=school, academic_year=year, is_active=True, wing=None)
    )
    return Outside(
        sections=sections,
        student_count=StudentEnrollment.objects.filter(
            class_group__in=sections, is_active=True
        ).count(),
    )


def floors_overview(school, year: str, when: dt.datetime) -> list[FloorPanel]:
    """الطابقان بأجنحتهما — بأربعة استعلاماتٍ مهما كثرت الأجنحة."""
    wings = list(
        Wing.objects.filter(school=school, academic_year=year, is_active=True)
        .select_related("supervisor")
        .prefetch_related(
            Prefetch(
                "class_groups",
                # والعامُ شرطٌ لا زينة: `class_groups` تُرجع كلَّ شعبةٍ أُسندت
                # إلى هذا الجناح في أيّ عام، والجناحُ سجلُّ عامٍ لا سجلُّ مبنى.
                # فشعبةٌ من عامٍ ماضٍ كانت تُعدّ في شُعبه وتُحسب في طلابه.
                queryset=ClassGroup.objects.filter(
                    is_active=True, academic_year=year
                ).select_related("time_band"),
                to_attr="live_sections",
            ),
            Prefetch("coverages", queryset=WingCoverage.objects.select_related("substitute")),
        )
        .order_by("order", "code")
    )
    counts = dict(
        StudentEnrollment.objects.filter(class_group__wing__in=wings, is_active=True)
        .values_list("class_group__wing_id")
        .annotate(total=Count("id"))
    )
    day_type = day_type_for(when.date())
    table = bells_for(school, day_type) if day_type else {}
    moment = when.time()

    cards = []
    day = when.date()
    for wing in wings:
        # من الجلب المسبق لا باستعلامٍ لكلّ جناح.
        cover = next((c for c in wing.coverages.all() if c.covers(day)), None)
        bands = bands_of(wing.live_sections)
        bells = [table[band.code] for band in bands if band.code in table]
        cards.append(
            WingCard(
                wing=wing,
                sections=wing.live_sections,
                student_count=counts.get(wing.id, 0),
                holder=(cover.substitute if cover else wing.supervisor),
                coverage=cover,
                bands=bands,
                bells=bells,
                positions=[
                    Position(
                        bell=bell, running=bell.running(moment), upcoming=bell.upcoming(moment)
                    )
                    for bell in bells
                ],
                off_floor=[band for band in bands if band.floor != wing.floor],
            )
        )

    return [
        FloorPanel(
            code=code,
            label=label,
            bells=[bell for bell in table.values() if bell.floor == code],
            wings=[card for card in cards if card.wing.floor == code],
        )
        for code, label in FLOORS
    ]


def substitute_pool(school, wing=None, on_date=None):
    """من يصلح بديلاً — ومن هو مشغولٌ منهم يُعرض مشغولاً لا يُحجب.

    الحجبُ يُخفي السبب: من يبحث عن زميلٍ فلا يجده في القائمة يظنّه غيرَ مؤهّل،
    وهو مؤهّلٌ يغطّي جناحاً آخر. فيُعرض الجميعُ ومعهم حالُهم، والقيدُ في
    `clean()` يمنع الخطأ لا القائمة.
    """
    day = on_date or timezone.localdate()
    held = dict(
        Wing.objects.filter(school=school, is_active=True, supervisor__isnull=False).values_list(
            "supervisor_id", "name"
        )
    )
    busy = {
        cover.substitute_id: cover.wing.name
        for cover in WingCoverage.objects.filter(wing__school=school)
        .filter(Q(end_date__isnull=True) | Q(end_date__gte=day))
        .select_related("wing")
    }
    people = (
        CustomUser.objects.filter(
            id__in=Membership.objects.filter(
                school=school, is_active=True, role__name__in=WingCoverage.SUBSTITUTE_ROLES
            ).values("user_id")
        )
        .distinct()
        .order_by("full_name")
    )
    own = wing.supervisor_id if wing is not None else None
    return [
        {
            "user": person,
            "is_own_supervisor": person.id == own,
            "principal_of": held.get(person.id, ""),
            "busy_with": busy.get(person.id, ""),
        }
        for person in people
    ]


def coverage_rows(school, year: str, on_date=None):
    """الأجنحةُ الخمسةُ وحالُ كلٍّ منها اليوم — أصيلٌ أو بديلٌ إلى متى."""
    day = on_date or timezone.localdate()
    wings = (
        Wing.objects.filter(school=school, academic_year=year, is_active=True)
        .select_related("supervisor")
        .prefetch_related(
            Prefetch(
                "coverages",
                queryset=WingCoverage.objects.select_related("substitute", "assigned_by"),
            )
        )
        .order_by("order", "code")
    )
    rows = []
    for wing in wings:
        active = next((c for c in wing.coverages.all() if c.covers(day)), None)
        rows.append(
            {
                "wing": wing,
                "coverage": active,
                "holder": active.substitute if active else wing.supervisor,
                "history": sorted(
                    (c for c in wing.coverages.all() if not c.covers(day)),
                    key=lambda c: c.start_date,
                    reverse=True,
                )[:5],
            }
        )
    return rows


def bell_tables(school) -> list[BellTable]:
    """جدولا اليومين — الأحد إلى الأربعاء، والخميس."""
    return [
        BellTable(day_type=day_type, label=label, bells=list(bells_for(school, day_type).values()))
        for day_type, label in ((REGULAR, "الأحد – الأربعاء"), (THURSDAY, "الخميس"))
    ]


@dataclass(frozen=True)
class SectionToRecord:
    """شعبةٌ في شاشة الرصد — ما يلزم لاختيارها والحكم عليها."""

    class_group: ClassGroup
    students: int
    periods: int
    confirmation: object

    @property
    def is_recorded(self) -> bool:
        return self.confirmation is not None

    @property
    def says(self) -> str:
        if self.confirmation is None:
            return "لم تُرصد"
        c = self.confirmation
        parts = [f"غياب {c.absent_count}"]
        if c.late_count:
            parts.append(f"تأخّر {c.late_count}")
        return " · ".join(parts)


def sections_to_record(wing, day) -> list[SectionToRecord]:
    """شُعبُ الجناح وحالُ رصدِها اليوم — ومنه «شُعبي المتبقّية n/5»."""
    done = confirmations_of(wing, day)
    rows = []
    for klass in wing.class_groups.filter(is_active=True):
        rows.append(
            SectionToRecord(
                class_group=klass,
                students=enrolled_of(klass).count(),
                periods=slots_of(klass, day),
                confirmation=done.get(klass.id),
            )
        )
    return rows


def wings_of(user, school, year):
    """أجنحةُ هذا المستخدم — ما يحمله اليوم أصيلاً أو بديلاً.

    والقيادةُ ترى الخمسةَ: المرحلة 3ب لم تُبنَ بعد، والتضييقُ هناك لا هنا.
    """
    all_wings = list(
        Wing.objects.filter(school=school, academic_year=year, is_active=True)
        .select_related("supervisor")
        .prefetch_related("coverages", "class_groups")
        .order_by("order", "code")
    )
    if user.is_superuser or user.get_role() in (
        "principal",
        "vice_admin",
        "vice_academic",
        "platform_developer",
    ):
        return all_wings
    return [w for w in all_wings if w.current_supervisor() == user]

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

from django.db.models import Count, Prefetch

from core.models import ClassGroup, StudentEnrollment, Wing
from core.models.academic import FLOORS, bands_of
from operations.bells import REGULAR, THURSDAY, Bell, Position, bells_for, day_type_for


@dataclass(frozen=True)
class WingCard:
    """جناحٌ كما يُقرأ في الشاشة."""

    wing: Wing
    sections: list[ClassGroup]
    student_count: int
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
            )
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
    for wing in wings:
        bands = bands_of(wing.live_sections)
        bells = [table[band.code] for band in bands if band.code in table]
        cards.append(
            WingCard(
                wing=wing,
                sections=wing.live_sections,
                student_count=counts.get(wing.id, 0),
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


def bell_tables(school) -> list[BellTable]:
    """جدولا اليومين — الأحد إلى الأربعاء، والخميس."""
    return [
        BellTable(day_type=day_type, label=label, bells=list(bells_for(school, day_type).values()))
        for day_type, label in ((REGULAR, "الأحد – الأربعاء"), (THURSDAY, "الخميس"))
    ]

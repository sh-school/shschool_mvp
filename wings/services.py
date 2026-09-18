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

from core.models import (
    ClassGroup,
    CustomUser,
    Membership,
    School,
    StudentEnrollment,
    Wing,
    WingCoverage,
)
from core.models.academic import FLOORS, bands_of
from operations.absence_policy import Gate
from operations.bells import REGULAR, THURSDAY, Bell, Position, bells_for
from operations.day_attendance import enrolled_of
from operations.school_days import SchoolDay, school_day


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

    @property
    def width_weight(self) -> float:
        """نصيبُ الطابق من عرض السطر: جناحٌ بواحد، وذو الجرسين بواحدٍ ونصف
        — لأنّه يقول موضعين في سطرٍ واحد."""
        return max(1, sum(1.5 if card.is_split else 1 for card in self.wings))


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
    def title(self) -> str:
        """عنوانُ بطاقة الجدول — يُبنى هنا لا في القالب."""
        return f"التوقيت — {self.label}"

    @property
    def columns(self) -> list[BellColumn]:
        """الأجراسُ المتطابقةُ خاناتٍ عمودٌ واحد — والمختلفةُ أعمدةٌ متجاورة.

        التاسعُ والثانويُّ في الطابق الأوّل يرنّان معاً من الأحد إلى الأربعاء،
        فعمودان لهما يكرّران تسعةَ أسطرٍ حرفاً بحرف. ويوم الخميس يفترقان،
        فيفترق عموداهما. فالدمجُ بالخانات لا بالاسم.
        """
        columns: list[BellColumn] = []
        for bell in self.bells:
            twin = next((c for c in columns if _reads_the_same(c.slots, bell.slots)), None)
            if twin:
                twin.bells.append(bell)
            else:
                columns.append(BellColumn(bells=[bell]))
        return columns

    @property
    def rows(self) -> list[list]:
        columns = self.columns
        depth = max((len(column.slots) for column in columns), default=0)
        return [
            [column.slots[index] if index < len(column.slots) else None for column in columns]
            for index in range(depth)
        ]


def _reads_the_same(a, b) -> bool:
    """خاناتٌ تُقرأ واحدةً: الاسمُ والوقتُ — لا رقمُ الصفّ الداخليّ في الإعدادات."""
    return [(s.label, s.start, s.end, s.is_break) for s in a] == [
        (s.label, s.start, s.end, s.is_break) for s in b
    ]


@dataclass
class BellColumn:
    """عمودٌ في جدول التوقيت: جرسٌ أو أجراسٌ خاناتُها واحدة."""

    bells: list[Bell]

    @property
    def slots(self):
        return self.bells[0].slots

    @property
    def name(self) -> str:
        """«التاسع 3·4 والثانويّ 10–12 (الطابق الأوّل)» — والطابقُ المشترك يُقال مرّة."""
        names = [bell.band_name for bell in self.bells]
        if len(names) == 1:
            return names[0]
        tails = {name.rsplit(" (", 1)[1] for name in names if " (" in name}
        if len(tails) == 1 and all(" (" in name for name in names):
            heads = [name.rsplit(" (", 1)[0] for name in names]
            return " و".join(heads) + " (" + tails.pop()
        return " و".join(names)


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


def floors_overview(
    school, year: str, when: dt.datetime, today: SchoolDay | None = None
) -> list[FloorPanel]:
    """الطابقان بأجنحتهما — بأربعة استعلاماتٍ مهما كثرت الأجنحة.

    و`today` يومُ `when` من التقويم إن قرأه المستدعي — وإلّا قُرئ هنا باستعلامٍ خامس.
    فالجرسُ لا يرنّ يومَ إجازة: ثلاثاؤها كان يُظهر «الحصّةَ الثالثة» في كلّ جناح.
    """
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
    today = today or school_day(school, when.date())
    day_type = today.bell_day_type
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
    """شعبةٌ في فهرس الرصد — أرقامُ آخر حصّةٍ مثبّتة، ونقطةٌ لكلّ حصّة."""

    class_group: ClassGroup
    students: int
    periods: list
    statuses: list

    @property
    def is_recorded(self) -> bool:
        """لا حصّةَ جاريةً ولا فائتةً تنتظر التثبيت."""
        return bool(self.periods) and not any(s in ("current", "missed") for s in self.statuses)

    @property
    def shown(self):
        """آخرُ حصّةٍ ثُبّتت — أرقامُها ما تعرضه البطاقة."""
        confirmed = [p for p in self.periods if p.confirmation is not None]
        return confirmed[-1] if confirmed else None

    @property
    def dots(self) -> list:
        return list(zip(self.periods, self.statuses, strict=True))

    @property
    def missed(self) -> int:
        return self.statuses.count("missed")


def sections_to_record(wing, day, now=None) -> list[SectionToRecord]:
    """شُعبُ الجناح وحالُ رصدِ حصصها — ومنه «المتبقّية n من 5» ونقاطُ الحصص."""
    from operations.period_register import periods_of

    now = now or timezone.now()
    rows = []
    for klass in wing.class_groups.filter(is_active=True).order_by("grade", "section"):
        periods = periods_of(klass, day)
        rows.append(
            SectionToRecord(
                class_group=klass,
                students=enrolled_of(klass).count(),
                periods=periods,
                statuses=[p.status(day, now) for p in periods],
            )
        )
    return rows


@dataclass(frozen=True)
class WatchRow:
    """طالبٌ يستحقّ نظرةَ المشرف اليوم — ولماذا."""

    student: CustomUser
    class_group: ClassGroup
    days: int
    gate: Gate | None
    passed: tuple
    needs_contact: dt.date | None

    @property
    def says(self) -> str:
        if self.passed:
            return f"تجاوز {self.passed[-1].label} ({self.passed[-1].max_days} يوماً)"
        if self.gate is not None:
            left = self.gate.max_days - self.days
            return f"{self.gate.label} بعد {left} يوم" if left > 0 else f"عند {self.gate.label}"
        return ""


def supervisor_watchlist(user: CustomUser, school: School, year: str, day: dt.date) -> dict:
    """ما ينتظر المشرفَ اليوم في أجنحته (لوحتُه، النسخةُ الأولى — قرارُ 2026-09-13).

    - **ينتظرون إخطارَ وليّ الأمر**: غابوا أمس ولم يُتّصل بأهلهم (م 3.4.1.5: الإخطارُ في
      اليوم نفسِه).
    - **عند العتبات**: من تجاوز عتبةَ غيابٍ بلا عذر، أو بقي له يومٌ واحدٌ عليها —
      فالإجراءُ بيد المشرف من أوّل عتبة (م 3.4.1.2).

    استعلامان لكلّ شعبة (الأيّامُ والإخطار) لا لكلّ طالب.
    """
    from operations.absence_policy import breached, next_gate
    from operations.absence_standing import unexcused_days_for_class
    from operations.guardian_contact import awaiting_contact
    from wings.scope import student_scope

    scope = student_scope(user, school)
    in_scope = scope.student_ids() if scope.is_wing_bound else None
    contacts: list[WatchRow] = []
    gates: list[WatchRow] = []
    for wing in wings_of(user, school, year):
        for klass in wing.class_groups.filter(is_active=True).order_by("grade", "section"):
            awaiting = awaiting_contact(klass, day)
            days_of = unexcused_days_for_class(klass, school, day)
            if not awaiting and not days_of:
                continue
            for enrollment in enrolled_of(klass):
                sid = enrollment.student_id
                if in_scope is not None and sid not in in_scope:
                    continue  # قيدُه الجاري في جناحٍ آخر — لا يُنبَّه عنه هنا
                days = days_of.get(sid, 0)
                gate = next_gate(klass.grade, days)
                passed = breached(klass.grade, days)
                row = WatchRow(enrollment.student, klass, days, gate, passed, awaiting.get(sid))
                if row.needs_contact:
                    contacts.append(row)
                if days and (passed or (gate is not None and gate.max_days - days <= 1)):
                    gates.append(row)
    gates.sort(key=lambda r: -r.days)
    return {"awaiting_contact": contacts, "at_gates": gates}


def next_section_awaiting(klass: ClassGroup, day: dt.date, start: dt.time) -> ClassGroup | None:
    """الشعبةُ التالية في جناح `klass` التي لم تُثبَّت حصّتُها الواقعةُ في `start` بعد.

    المشرفُ يمرّ على شُعبه الخمس في الحصّة نفسِها، فبعد تثبيت واحدةٍ يُنقل إلى
    التي تليها بترتيب الفهرس — ويُدار عليها دورةً كاملة، فلا تُهمل شعبةٌ قبله.
    ولا شعبةَ بلا حصّةٍ في تلك الساعة (اختيارٌ أو فراغ) ولا شعبةَ ثُبّتت.
    """
    from operations.models import PeriodConfirmation, Session

    wing = klass.wing
    if wing is None:
        return None
    ordered: list[ClassGroup] = list(
        wing.class_groups.filter(is_active=True).exclude(pk=klass.pk).order_by("grade", "section")
    )
    after = [c for c in ordered if (c.grade, c.section) > (klass.grade, klass.section)]
    before = [c for c in ordered if (c.grade, c.section) <= (klass.grade, klass.section)]
    ids = [c.pk for c in after + before]
    if not ids:
        return None
    scheduled = set(
        Session.objects.filter(class_group_id__in=ids, date=day, start_time=start)
        .exclude(status="cancelled")
        .values_list("class_group_id", flat=True)
    )
    confirmed = set(
        PeriodConfirmation.objects.filter(
            class_group_id__in=ids, date=day, start_time=start
        ).values_list("class_group_id", flat=True)
    )
    for candidate in after + before:
        if candidate.pk in scheduled and candidate.pk not in confirmed:
            return candidate
    return None


def wings_of(user: CustomUser, school: School, year: str) -> list[Wing]:
    """أجنحةُ هذا المستخدم — ما يحمله اليوم أصيلاً أو بديلاً.

    **اليومُ لا التاريخُ المعروض، عمداً.** من يحمل الجناحَ اليوم يرى أيّامَه
    السابقة ويصحّحها (عذرٌ بعد عودة الطالب، حصّةٌ فاتت أيّامَ التغطية)، ومن
    انتهى تكليفُه لا يعود إليه بتاريخٍ قديم في الرابط — فالتاريخُ مُدخَلٌ من
    المستخدم، والصلاحيّةُ لا تُبنى عليه. والكشفُ المطبوعُ يسمّي حاملَ ذلك
    اليوم (`wing_register`)، فالسجلُّ صادقٌ والوصولُ أضيق.

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


def record_panels(user, school, year, day) -> list[dict]:
    """ألواحُ الرصد: لكلّ جناحٍ يحمله المستخدمُ شُعبُه وحالُ رصدِها.

    يقرؤها فهرسُ الرصد ولوحةُ المشرف الرئيسيّة معاً — فلا يُحسب «المتبقّي»
    في موضعين فيختلفا.
    """
    panels = []
    for wing in wings_of(user, school, year):
        rows = sections_to_record(wing, day)
        done = sum(1 for r in rows if r.is_recorded)
        panels.append(
            {
                "wing": wing,
                "rows": rows,
                "done": done,
                "total": len(rows),
                "remaining": len(rows) - done,
            }
        )
    return panels

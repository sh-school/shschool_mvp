"""operations/services/schedule_retention.py — إحالةُ ما مضى إلى الأرشيف وضبطُ ما يُحتفَظ به منه.

مقطعٌ من `ScheduleService` (البند 8، الخطوة 2): يُركَّب في `schedule.py`.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from core.academic_calendar import (
    AcademicCalendar,
)
from operations.models import (
    ScheduleGeneration,
    ScheduleSlot,
    SubjectClassAssignment,
)

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from core.models import School


class ScheduleRetentionMixin:
    @classmethod
    def retire_past_year_slots(cls, school: School, on=None) -> int:
        """يُطفئ كلَّ حصّةٍ نشطةٍ خارج العام الجاري — ويُعيد عددَ ما أُطفئ.

        عامٌ جديدٌ يبدأ بتاريخٍ لا بزرّ: `AcademicCalendar` يشتقّه من تقويم
        الوزارة، فيتبدّل الجوابُ ليلةَ الأوّل من سبتمبر بلا أن يلمس أحدٌ
        شيئاً. وجدولُ العام الماضي يبقى نشطاً في القاعدة كما تركه — فتصير
        في المدرسة الواحدة جداولُ عامين نشطةً معاً.

        وقد وقع هذا فعلاً: بقيت مئتان وخمسون حصّةً من 2025-2026 نشطةً بعد
        دخول 2026-2027، وتسعةٌ من معلّميها العشرة يدرّسون في العام الجديد،
        فكانوا يُرَون مشغولين في أوقاتٍ هم فيها متفرّغون.

        وهي ثابتةُ التكرار: نداؤها مرّتين لا يُطفئ شيئاً في الثانية. ولا
        تحذف — الحذفُ قرارُ `prune_schedule_slots` بيد إنسان.
        """
        return cls._retire(ScheduleSlot, school, on, "حصّة")

    @classmethod
    def retire_past_year_assignments(cls, school: School, on=None) -> int:
        """يُطفئ كلَّ إسنادِ مادّةٍ نشطٍ خارج العام الجاري — ويُعيد عددَ ما أُطفئ.

        والإسنادُ أصلُ الجدول لا نتيجتُه: منه يُولَّد. فإسنادُ عامٍ مضى باقٍ
        نشطاً يُدخل شُعباً منقضيةً في مصفوفة التوليد، ويُحسب في نصاب المعلّم،
        ويُرجّح معلّماً على غيره في اقتراح البديل بحكم مادّةٍ لم يعد يدرّسها.
        """
        return cls._retire(SubjectClassAssignment, school, on, "إسناداً")

    @classmethod
    def retire_past_year_records(cls, school: School, on=None) -> dict[str, int]:
        """الحارسُ كاملاً: الإسنادُ ثمّ الجدول — وهذا ما تنادِيه المواضعُ الثلاثة."""
        return {
            "assignments": cls.retire_past_year_assignments(school, on),
            "slots": cls.retire_past_year_slots(school, on),
        }

    # ── النسخُ المؤرشفة ─────────────────────────────────────────────
    @staticmethod
    def retained_archived_ids(school: School, academic_year: str, keep: int | None = None) -> list:
        """معرّفاتُ التوليدات المؤرشفة التي تُبقى — الأحدثُ فالأحدث بعدد `keep`.

        مصدرٌ واحدٌ لتعريف «المُبقى» يستعمله الاعتمادُ والأمرُ معاً، فلا يحذف
        أحدُهما ما يحفظه الآخر.
        """
        from django.conf import settings

        if keep is None:
            keep = int(getattr(settings, "SCHEDULE_ARCHIVE_RETENTION", 0))
        if keep <= 0:
            return []
        return list(
            ScheduleGeneration.objects.filter(
                school=school, academic_year=academic_year, status="archived"
            )
            .order_by("-generated_at")
            .values_list("id", flat=True)[:keep]
        )

    @classmethod
    def retain_archived_generations(
        cls, school: School, academic_year: str, keep: int | None = None
    ) -> int:
        """يحذف التوليداتِ المؤرشفةَ الزائدةَ على `keep` — وحصصُها الميّتة معها.

        القرار (2026-09-05): جدولٌ واحدٌ فقط، الحيّ. فالافتراضُ صفر: ما يُؤرشف
        يذهب عند الاعتماد التالي. والمسودّاتُ والفاشلُ خارجَ هذا كلِّه — الأولى
        عملٌ جارٍ، والثاني سجلُّ إخفاقٍ بلا حصص.

        والحذفُ يمرّ بحارس `ScheduleGenerationQuerySet`: توليدٌ له حصّةٌ حيّةٌ لا
        يُمسّ ولو كانت حالتُه «مؤرشف» — فلا يُفقد الجدولُ الحيّ نسبَه أبداً.

        يُعيد عددَ التوليدات المحذوفة.
        """
        keep_ids = cls.retained_archived_ids(school, academic_year, keep)
        stale = (
            ScheduleGeneration.objects.filter(
                school=school, academic_year=academic_year, status="archived"
            )
            .exclude(id__in=keep_ids)
            .exclude(slots__is_active=True)
            .distinct()
        )
        count = stale.count()
        if count:
            ScheduleGeneration.objects.filter(
                id__in=list(stale.values_list("id", flat=True))
            ).delete()
            logger.info(
                "retain_archived_generations: حُذف %d توليداً مؤرشفاً في %s/%s (المُبقى %d)",
                count,
                school.code,
                academic_year,
                len(keep_ids),
            )
        return count

    @staticmethod
    def _retire(model, school: School, on, noun: str) -> int:
        """الإطفاءُ المشترك — استعلامٌ واحد: `UPDATE` يُعيد عددَ ما مسّه.

        **ولا يعمل إلّا بعامٍ من التقويم.** فـ`academic_year_for_school` ترتدّ
        إلى الثابت المجمَّد حين لا يغطّي اليومَ عامٌ مبذور — والثابتُ يتقادم
        صامتاً (هو اليوم «2025-2026»). فلو أطفأنا على ذلك الجواب لأطفأنا
        جدولَ العام الجاري كلَّه في مدرسةٍ نسيت بذرَ تقويمها. حارسٌ يخطئ
        بالسكوت خيرٌ من حارسٍ يخطئ بالفعل.

        وكان عدّاً ثمّ كتابة، وهذا يمرّ في مسار الطلب مرّةً كلَّ يومٍ لكلّ
        مدرسة — فمسحُ الجدول مرّتين ليأتيَ الجوابُ صفراً في أغلب الأيام تَرَفٌ.
        """
        year = AcademicCalendar.current(school, on).year
        if year is None:
            logger.warning(
                "retire_past_year: لا عامَ في تقويم %s يغطّي اليوم — لا يُطفأ شيء",
                school.name,
            )
            return 0

        count = (
            model.objects.past_years(school, year=year.name)
            .filter(is_active=True)
            .update(is_active=False)
        )
        if count:
            logger.info(
                "retire_past_year: أُطفئ %d %s خارج عام %s في %s",
                count,
                noun,
                year.name,
                school.name,
            )
        return count

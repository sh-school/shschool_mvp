"""إبلاغُ الأسرة بمخالفات الرصد — فوراً للهروب من المدرسة، وملخّصاً يوميّاً لما سواه.

## القرار (المالك، 2026-09-16)

كشفُ الحصص يُنشئ مخالفاتٍ بلا يدٍ بشريّة (`BehaviorInfraction.auto_rule`)، ولم يكن
يبلغ الأسرةَ منها شيء. فصار:

- **الهروبُ من المدرسة** (3-10، الدرجة الثالثة) يُبلَّغ **فوراً** بعد الالتزام، بمسار
  المخالفة اليدويّة نفسِه (`notify_behavior_task` ← `BehaviorService.notify_parents`)،
  فتتطابق الصياغةُ والقنواتُ مع مخالفةٍ يدويّةٍ من درجتها. خروجُ طالبٍ من المدرسة
  أمرُ سلامةٍ لا ينتظر العصر.
- **التأخّرُ عن الحصّة والهروبُ منها** في **ملخّصٍ واحدٍ** لكلّ طالبٍ في كلّ يومٍ
  دراسيّ، الساعة 15:00 من الأحد إلى الخميس (`behavior.send_auto_infraction_digest`).
  رسالةٌ لكلّ حصّةٍ كانت ستُغرق الأسرةَ بسبع رسائل في يومٍ واحد.

## ما يحمله الملخّص — تقليلُ البيانات

العددُ والتاريخُ والإحالةُ إلى البوابة، ولا شيءَ سواها — في كلّ القنوات. الـHub
لا يفرّق نصَّ الجرس عن نصّ واتساب والبريد، ورقمُ الحصّة ومادّتُها تفصيلٌ يخرج إلى
مزوّدين لا نملك حفظَهم؛ والبوابةُ تعرضه لمن يحقّ له.

## ما يُقرأ، ومتى

- **اليومُ يومُ الحصّة** (`session__date`) لا `BehaviorInfraction.date`: ذاك يومُ
  الكتابة، وتصحيحُ حصّةٍ مضت يُكتب اليومَ عن يومها.
- **الحالةُ النهائيّةُ ساعةَ الإرسال**: ما أزاله تصحيحٌ قبلها لا يُذكر، والحصّةُ
  الملغاةُ لا تُذكر مخالفتُها (`_sync_rule` لا يرى الملغاة فلا يُزيل ما تحتها).
- **لا يُعاد ما أُرسل**: `AutoInfractionNotice` صفٌّ لكلّ مخالفةٍ بُلِّغ بها، بقيدٍ
  فريدٍ على (الطالب، اليوم، القاعدة، بدء الحصّة)، يُكتب في معاملة الإرسال نفسِها.
- **وما جدّ بعد الإرسال يُرسَل إضافةً**: تصحيحٌ بعد 15:00 يُنشئ مخالفةً ليومٍ أُرسل
  ملخّصُه، فيحملها التشغيلُ التالي وحدَها بعنوانٍ يسمّي يومَها.
- **ويُمسح آخرُ خمسة أيّامٍ دراسيّة** في كلّ تشغيل: شاشةُ الأجنحة تقبل تصحيحَ أيّ
  يومٍ مضى، وخدمةُ Beat قد تغيب يوماً.

## من يستلم

أولياءُ الأمور المربوطون بـ`can_view_behavior=True` — كما تعرض `parent_behavior` —
ناقصاً من سحب موافقتَه على بيانات السلوك (`_filter_consent`، PDPPL).
"""

from __future__ import annotations

import datetime as dt
import logging
import uuid
from typing import TYPE_CHECKING, Any

from django.db import IntegrityError, transaction
from django.urls import reverse
from django.utils import timezone

from behavior.models import AutoInfractionNotice, BehaviorInfraction
from behavior.notify import notify_behavior_after_commit

if TYPE_CHECKING:
    from collections.abc import Iterable

    from core.models import CustomUser, School

logger = logging.getLogger(__name__)

#: حدثُ الـHub — مسجَّلٌ في قنواته وأولويّته وموافقته (`notifications/hub.py`).
EVENT = "behavior_digest"

#: تُبلَّغ فوراً — بمسار المخالفة اليدويّة.
IMMEDIATE_RULES = ("school_escape",)

#: تُجمع في الملخّص اليوميّ.
DIGEST_RULES = ("period_tardy", "class_escape")

#: كم يوماً دراسيّاً يُمسح إلى الوراء في كلّ تشغيل — اليومُ منها.
CATCH_UP_SCHOOL_DAYS = 5

#: مفتاحُ المخالفة في عين الأسرة: الطالبُ والقاعدةُ وبدءُ الحصّة (واليومُ ثابتٌ في النداء).
Key = tuple[Any, str, dt.time]

#: مخالفةٌ وبدءُ حصّتها — البدءُ جزءُ المفتاح.
Item = tuple[BehaviorInfraction, dt.time]


# ══════════════════════════════════════════════════════════════════
#  الصياغة
# ══════════════════════════════════════════════════════════════════


def count_phrase(count: int) -> str:
    """العددُ ومعدودُه بإعراب العربيّة: واحدةٌ، مثنًّى، جمعٌ للعشرة فما دونها، ومفردٌ منصوبٌ فوقها."""
    if count == 1:
        return "مخالفةٌ آليّةٌ واحدة"
    if count == 2:
        return "مخالفتان آليّتان"
    if 3 <= count <= 10:
        return f"{count} مخالفاتٍ آليّة"
    return f"{count} مخالفةً آليّة"


def day_label(day: dt.date) -> str:
    """«13/9» — كما يُكتب اليومُ في شاشات المدرسة، بلا صفرٍ ولا سنة."""
    return f"{day.day}/{day.month}"


def digest_title(student_name: str, day: dt.date, *, today: dt.date, supplement: bool) -> str:
    if supplement:
        return f"إضافةٌ إلى ملخّص سلوك يوم {day_label(day)} — {student_name}"
    if day == today:
        return f"ملخّص سلوك اليوم — {student_name}"
    return f"ملخّص سلوك يوم {day_label(day)} — {student_name}"


def digest_body(count: int, day: dt.date) -> str:
    return (
        f"رُصدت لابنكم {count_phrase(count)} في كشف الحصص يوم {day_label(day)}. "
        "التفاصيل في بوابة وليّ الأمر."
    )


# ══════════════════════════════════════════════════════════════════
#  الفوريّ — الهروب من المدرسة
# ══════════════════════════════════════════════════════════════════


def notify_immediately(infraction: BehaviorInfraction, school: School, by: CustomUser) -> bool:
    """يُسجّل الإبلاغَ بمخالفةٍ فوريّةٍ أنشأها الرصد، ويؤجّل الإرسالَ إلى الالتزام.

    يُستدعى داخل معاملة الرصد: إن تراجعت تراجعت العلامةُ ولم يُرسَل شيء. ومخالفةٌ
    أُبلغ بها ثمّ أزالها تصحيحٌ ثمّ أعادها تصحيحٌ آخر لا تُرسَل ثانيةً — ويُرجع
    `False` حينها.
    """
    session = infraction.session
    if session is None or infraction.auto_rule not in IMMEDIATE_RULES:
        return False
    try:
        with transaction.atomic():
            AutoInfractionNotice.objects.create(
                school=school,
                student=infraction.student,
                date=session.date,
                auto_rule=infraction.auto_rule,
                start_time=session.start_time,
                infraction=infraction,
                kind="immediate",
            )
    except IntegrityError:
        return False

    # المسارُ اليدويُّ بعينه: الطبرُ بعد الالتزام، واحتواءُ فشل الوسيط داخله.
    transaction.on_commit(
        lambda: notify_behavior_after_commit(infraction, school, by),
        robust=True,
    )
    return True


# ══════════════════════════════════════════════════════════════════
#  الملخّص
# ══════════════════════════════════════════════════════════════════


def school_days_back(today: dt.date, count: int = CATCH_UP_SCHOOL_DAYS) -> list[dt.date]:
    """آخرُ `count` يوماً دراسيّاً حتى `today` — الأقدمُ أوّلاً، فتصل الرسائلُ بترتيبها."""
    from operations.bells import day_type_for

    days: list[dt.date] = []
    day = today
    while len(days) < count:
        if day_type_for(day):
            days.append(day)
        day -= dt.timedelta(days=1)
    return days[::-1]


def _pending_on(school: School, day: dt.date) -> tuple[dict[Any, list[Item]], set[Any]]:
    """(ما لم يُبلَّغ به بعدُ لكلّ طالب، ومن أُرسل له ملخّصُ هذا اليوم من قبل)."""
    sent = set(
        AutoInfractionNotice.objects.filter(
            school=school, date=day, auto_rule__in=DIGEST_RULES
        ).values_list("student_id", "auto_rule", "start_time")
    )
    digested = {student_id for student_id, _, _ in sent}

    pending: dict[Any, list[Item]] = {}
    seen: set[Key] = set()
    infractions = (
        BehaviorInfraction.objects.filter(
            school=school, session__date=day, auto_rule__in=DIGEST_RULES
        )
        .exclude(session__status="cancelled")
        .select_related("student", "session")
        .order_by("student_id", "session__start_time", "auto_rule")
    )
    for infraction in infractions:
        session = infraction.session
        if session is None:  # لا يقع: `session__date` لا يطابق حصّةً فارغة
            continue
        key: Key = (infraction.student_id, infraction.auto_rule, session.start_time)
        if key in sent or key in seen:
            continue
        seen.add(key)
        pending.setdefault(infraction.student_id, []).append((infraction, session.start_time))
    return pending, digested


def _parents_of(student: CustomUser, school: School) -> list[CustomUser]:
    """من يرى سلوكَ الطالب في البوابة، ناقصاً من سحب موافقتَه."""
    from core.models import ParentStudentLink
    from notifications.hub import _filter_consent

    parents = [
        link.parent
        for link in ParentStudentLink.objects.filter(
            student=student, school=school, can_view_behavior=True
        ).select_related("parent")
    ]
    kept: list[CustomUser] = _filter_consent(parents, EVENT, school, student)
    return kept


def _send_one(
    school: School,
    day: dt.date,
    items: list[Item],
    *,
    supplement: bool,
    today: dt.date,
) -> bool:
    """علاماتُ الإبلاغ والإشعارُ في معاملةٍ واحدة — ويُرجع هل خرجت رسالة.

    العلاماتُ أوّلاً في نقطة حفظٍ داخليّة: إن سبقنا تشغيلٌ متزامنٌ إليها أسقطها
    القيدُ الفريد فتُترك الرسالةُ له. وإن فشل الإرسالُ بعدها تراجعت معه، فيُعيدها
    التشغيلُ التالي.
    """
    from notifications.hub import NotificationHub

    student = items[0][0].student
    message_id = uuid.uuid4()
    with transaction.atomic():
        recipients = _parents_of(student, school)
        try:
            with transaction.atomic():
                AutoInfractionNotice.objects.bulk_create(
                    [
                        AutoInfractionNotice(
                            school=school,
                            student=student,
                            date=day,
                            auto_rule=infraction.auto_rule,
                            start_time=start,
                            infraction=infraction,
                            message_id=message_id,
                            kind="supplement" if supplement else "digest",
                            recipients=len(recipients),
                        )
                        for infraction, start in items
                    ]
                )
        except IntegrityError:
            logger.info(
                "auto digest already sent school_id=%s student_id=%s day=%s",
                school.pk,
                student.pk,
                day,
            )
            return False
        if not recipients:
            return False
        NotificationHub.dispatch(
            event_type=EVENT,
            school=school,
            recipients=recipients,
            title=digest_title(student.full_name, day, today=today, supplement=supplement),
            body=digest_body(len(items), day),
            related_url=reverse("parent_behavior"),
            related_object_id=str(message_id),
            sent_by=None,
        )
    return True


def send_day(school: School, day: dt.date, *, today: dt.date | None = None) -> int:
    """يرسل ملخّصَ `day` (أو إضافتَه) لكلّ طالبٍ له ما لم يُبلَّغ به — ويُرجع عددَ الرسائل.

    يُستدعى داخل نطاق المدرسة (`school_rls_scope`). وطالبٌ يفشل إرسالُه لا يمنع
    غيرَه: يُرصد بمعرّفه، ويُعاد في التشغيل التالي لأنّ علاماته تراجعت.
    """
    today = today or timezone.localdate()
    pending, digested = _pending_on(school, day)
    sent = 0
    for student_id, items in pending.items():
        try:
            if _send_one(school, day, items, supplement=student_id in digested, today=today):
                sent += 1
        except Exception as exc:
            # [B4-7O] معرّفاتٌ ونوعُ الخطأ — لا اسمَ ولا نصَّ مخالفة.
            logger.exception(
                "auto digest failed school_id=%s student_id=%s day=%s error=%s",
                school.pk,
                student_id,
                day,
                type(exc).__name__,
            )
    return sent


def send_for_schools(
    days: Iterable[dt.date], *, today: dt.date, school_id: str | None = None
) -> dict[str, int]:
    """يمرّ على المدارس النشطة، كلٌّ في نطاقه، ويرسل ملخّصاتِ `days`.

    مدرسةٌ يفشل نطاقُها (عاملٌ مربوطٌ بمدرسةٍ أخرى) أو استعلامُها لا توقف البقيّة.
    """
    from core.celery_tasks import school_rls_scope
    from core.models import School

    days = list(days)
    schools = School.objects.filter(is_active=True)
    if school_id:
        schools = schools.filter(id=school_id)
    sent = failed = 0
    for school in schools.iterator(chunk_size=100):
        try:
            with school_rls_scope(school.id):
                for day in days:
                    sent += send_day(school, day, today=today)
        except Exception as exc:
            failed += 1
            logger.exception(
                "auto digest school failed school_id=%s error=%s", school.id, type(exc).__name__
            )
    return {"sent": sent, "failed_schools": failed}

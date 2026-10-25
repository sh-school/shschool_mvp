"""عدٌّ تجريبيٌّ لتجهيل أسماء القاصرين في سجلّ التدقيق القديم (D-186م ج، W-20261004-003).

سجلُّ التدقيق (`AuditLog`) ملحقٌ لا يُعدَّل، وكتبت المُلتقِطاتُ القديمةُ (قبل W-20261003-019) اسمَ
الطالب كاملاً في `object_repr` وفي `changes` لصفوفٍ عن طالب (`CustomUser`) وعن ربط وليّ الأمر
(`ParentStudentLink`، بصيغة «وليّ ← طالب (صلة)»). قرارُ المالك بصفته DPO: تمريرةٌ واحدةٌ **للقاصرين
وحدهم** بعد نسخةٍ احتياطيّةٍ وعدٍّ تجريبيٍّ بلا كتابةٍ يوافق عليه، **وتخطّي الأسماء المشتركة** مع
بالغ؛ وكادرُ البالغين يبقى.

هذا الأمرُ **عدٌّ فقط**: لا يكتب شيئاً في أيّ جدول، ولا يطبع اسماً — أعدادٌ لكلّ فئة. و`--apply`
مغلقٌ عمداً: التنفيذُ يتسلسل بعد W-20261004-002 (حالةٌ ثالثةٌ في زناد AuditLog بعلَم معاملة) ولا يُفتح قبل
نسخةٍ احتياطيّةٍ موثَّقة وموافقةِ المالك على هذه الأرقام وحكمِ 0105، ولا يُشغَّل على الإنتاج بغير المالك.

فئاتُ العدّ (كلُّ صفٍّ في فئةٍ واحدة):
    to_anonymize      اسمُ قاصرٍ غيرُ مشترك — سيُجهَّل
    skip_shared_name  اسمُ القاصر نفسُه اسمُ بالغٍ في النظام — يُتخطّى (لا يُعرف أيُّهما)
    skip_short_name   الاسمُ كلمةٌ واحدة — مطابقتُه النصّيّةُ ضعيفة فيُتخطّى
    no_minor_name     لا اسمَ قاصرٍ في الصفّ (معرّفٌ مقنَّع أو اسمُ بالغ فقط)

    python manage.py anonymize_minor_audit_names            # عدٌّ فقط
"""

import re
from argparse import ArgumentParser
from collections import Counter
from typing import Any

from django.core.management.base import BaseCommand, CommandError

from core.models import AuditLog, CustomUser, Membership, ParentStudentLink

#: النماذجُ التي يشملها التمرير (قرار D-186م ج): صفوفٌ عن طالب وعن ربط وليّ الأمر.
SCOPE_MODELS = ("CustomUser", "ParentStudentLink")
#: «وليّ ← طالب (صلة)» كما كان `ParentStudentLink.__str__` قبل التقنيع.
_LINK_REPR = re.compile(r"^(?P<parent>.+?) ← (?P<student>.+?) \(")

CATEGORIES = ("to_anonymize", "skip_shared_name", "skip_short_name", "no_minor_name")


def _minor_directory() -> dict[str, str]:
    """معرّفُ المستخدم ← اسمُه، للقاصرين: دورُ «طالب»، أو الطرفُ الطالبُ في ربط وليّ أمر."""
    ids = set(
        Membership.objects.filter(role__name="student").values_list("user_id", flat=True)
    ) | set(ParentStudentLink.objects.values_list("student_id", flat=True))
    return {
        str(pk): name
        for pk, name in CustomUser.objects.filter(pk__in=ids).values_list("pk", "full_name")
    }


def _row_texts(object_repr: str, changes: Any) -> list[str]:
    """النصوصُ التي قد تحمل اسماً: الوصفُ وقيمُ `changes` النصّيّةُ من المستوى الأوّل."""
    texts = [object_repr or ""]
    if isinstance(changes, dict):
        texts.extend(v for v in changes.values() if isinstance(v, str))
    return texts


def _classify(texts: list[str], candidates: set[str], adult_names: set[str]) -> str:
    """فئةُ صفٍّ واحد من أسماء القاصرين المرشَّحة له. الأسماءُ تُقارَن ولا تُطبع."""
    present = {n for n in candidates if n and any(n in t for t in texts)}
    if not present:
        return "no_minor_name"
    if any(len(n.split()) < 2 for n in present):
        return "skip_short_name"
    if present & adult_names:
        return "skip_shared_name"
    return "to_anonymize"


def plan_minor_name_anonymization() -> dict[str, Any]:
    """يعدّ ولا يكتب: أعدادٌ لكلّ فئةٍ ولكلّ نموذج. القراءةُ وحدَها (`SELECT`)."""
    minors = _minor_directory()
    minor_names = set(minors.values())
    adult_names = set(
        CustomUser.objects.exclude(pk__in=list(minors)).values_list("full_name", flat=True)
    )
    # مطابقةٌ نصّيّةٌ عامّةٌ لا تُجرى إلا بأسماء من كلمتين فأكثر؛ والأحاديّةُ تُعدّ تخطّياً صريحاً.
    multiword = {n for n in minor_names if len(n.split()) >= 2}

    by_model: dict[str, Counter] = {m: Counter() for m in SCOPE_MODELS}
    affected_ids: set[str] = set()
    rows = AuditLog.objects.filter(model_name__in=SCOPE_MODELS).values_list(
        "id", "model_name", "object_id", "object_repr", "changes"
    )
    for row_id, model_name, object_id, object_repr, changes in rows.iterator(chunk_size=2000):
        texts = _row_texts(object_repr, changes)
        if model_name == "CustomUser":
            own = minors.get(str(object_id))
            candidates = {own} if own else set()
        else:
            match = _LINK_REPR.match(object_repr or "")
            if match:
                candidates = {match.group("student")} & minor_names
            else:
                candidates = {n for n in multiword if any(n in t for t in texts)}
        category = _classify(texts, candidates, adult_names)
        by_model[model_name][category] += 1
        if category == "to_anonymize":
            affected_ids.add(str(row_id))

    totals = Counter()
    for counter in by_model.values():
        totals.update(counter)
    return {
        "by_model": {m: dict(c) for m, c in by_model.items()},
        "totals": {c: totals.get(c, 0) for c in CATEGORIES},
        "rows_in_scope": sum(totals.values()),
        "rows_to_anonymize": len(affected_ids),
        "minors_known": len(minors),
    }


class Command(BaseCommand):
    help = "عدٌّ تجريبيٌّ لتجهيل أسماء القاصرين في AuditLog (بلا كتابة ولا أسماء في المخرج)"

    def add_arguments(self, parser: ArgumentParser) -> None:
        parser.add_argument(
            "--apply",
            action="store_true",
            help="مغلقٌ عمداً: يتسلسل بعد W-20261004-002 وبعد نسخةٍ وموافقةٍ وحكم",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        if options["apply"]:
            raise CommandError(
                "التنفيذُ مغلق: لا يُفتح قبل W-20261004-002 (حالةٌ ثالثةٌ في زناد AuditLog)، ونسخةٍ احتياطيّةٍ "
                "موثَّقة، وموافقةِ المالك على العدّ، وحكمِ 0105. هذا الأمرُ يعدّ فقط."
            )
        report = plan_minor_name_anonymization()
        self.stdout.write(f"قاصرون معروفون: {report['minors_known']}")
        self.stdout.write(
            f"صفوفٌ في النطاق (CustomUser وParentStudentLink): {report['rows_in_scope']}"
        )
        for model_name, counts in report["by_model"].items():
            line = "، ".join(f"{c}={counts.get(c, 0)}" for c in CATEGORIES)
            self.stdout.write(f"{model_name}: {line}")
        totals = report["totals"]
        self.stdout.write("المجموع: " + "، ".join(f"{c}={totals[c]}" for c in CATEGORIES))
        self.stdout.write(self.style.WARNING("عدٌّ فقط — لم يُكتب شيء ولم يُجهَّل اسم."))

"""لوحةُ «مزامنةُ الخارطة» — طلباتٌ دُمجت ولم يُذكر رقمُها في أيِّ بندٍ من الخارطة بعدُ (MAE-11، W-20260928-017؛ D-50م).

القاعدةُ في `CLAUDE.md` («الخارطةُ الحيّةُ تُحدَّث بعد كلّ دمجٍ»): كلُّ جلسةٍ تُبلِغ «0701 · تحديث الخارطة» بعملها فورَ اندماج طلبها،
وكانت المطابقةُ يدويّةً فيتأخّر إغلاقُ البنود أو يُنسى. هنا تُحسب آليّاً: الطلباتُ المدموجةُ (GitHub العامّ، آخرُ مئةِ طلبٍ مغلق، عدا الآليّة
bots كـDependabot) مقابلَ الأرقام `#N` المذكورة في حقول `pr` و`note` و`ref` من بنود الخارطة. رقمٌ لا يُذكر في أيٍّ منها = «لم يُزامَن».

- **لا هجرةَ ولا لمسَ لـ`roadmap/`** (ملكُ «0701»): قراءةٌ فقط من جدول البنود.
- **أرقامٌ فقط في اللوحة** (`contract.py`: لا نصَّ ولا رقمَ طلبٍ من طرفٍ ثالث): العددُ وعمرُ الأقدم. وقائمةُ الأرقام نفسِها بأمرٍ
  `python manage.py roadmap_unsynced` — هو «طابورُ المزامنة» الذي تقرؤه 0701.
- **مهلةٌ طبيعيّة**: لا يُعدّ «متأخّراً» ما دُمج قبل أقلَّ من 24 ساعة (W-20260929-010: كانت 36). بعدها «انتبه».
  ولا أحمرَ: الخارطةُ خطّةٌ لا نظامٌ حيّ (كلوحة الخارطة).
- **المطابقةُ بحقل `pr` وحدَه** (W-20260929-010): الطلبُ «مُزامَنٌ» إن ورد في `RoadmapItem.pr` لبندٍ؛ وورودُه في `note` أو `ref` فقط
  لا يُزامنه (لا تتغيّر به حالةُ بندٍ ولا مرجعُه)، بل يُعدّ في مقياسٍ مستقلٍّ «مذكورٌ في ملاحظةٍ فقط» ليراه من يغلق البند.
"""

from __future__ import annotations

import re
import time
from typing import Any

from command_center import contract
from command_center.collectors import github
from command_center.collectors.publish import failed, publish
from roadmap.models import RoadmapItem

PANEL = "sync"
MERGED_PATH = "pulls?state=closed&sort=updated&direction=desc&per_page=100"
GRACE_HOURS = 24
_REF = re.compile(r"#(\d{2,6})\b")


def reduce_merged(payload: Any) -> dict[str, Any] | None:
    """أرقامُ الطلبات المدموجة وأزمنةُ دمجها، بلا عناوينَ ولا كتّاب؛ وتُستثنى الآليّةُ (bots)."""
    if not isinstance(payload, list):
        return None
    prs: list[list[float]] = []
    for pull in payload:
        if not isinstance(pull, dict) or not pull.get("merged_at"):
            continue
        raw_user = pull.get("user")
        user: dict[str, Any] = raw_user if isinstance(raw_user, dict) else {}
        if user.get("type") == "Bot" or str(user.get("login", "")).endswith("[bot]"):
            continue
        number, merged = pull.get("number"), github.epoch(pull.get("merged_at"))
        if isinstance(number, int) and not isinstance(number, bool) and merged is not None:
            prs.append([number, merged])
    return {"prs": prs, "full": len(payload) >= 100}


def _numbers(texts: tuple[str, ...]) -> set[int]:
    return {int(n) for text in texts for n in _REF.findall(text or "")}


def synced_numbers() -> set[int]:
    """الأرقامُ `#N` في حقل `pr` لأيّ بند — وحدَه هو المزامنة (W-20260929-010)."""
    found: set[int] = set()
    for (pr,) in RoadmapItem.objects.values_list("pr"):
        found |= _numbers((pr,))
    return found


def mentioned_numbers() -> set[int]:
    """الأرقامُ المذكورةُ في `pr` أو `note` أو `ref` — حدٌّ أعلى للمُزامَن، يُقارَن به لكشف «ذُكر في ملاحظةٍ فقط»."""
    found: set[int] = set()
    for pr, note, ref in RoadmapItem.objects.values_list("pr", "note", "ref"):
        found |= _numbers((pr, note, ref))
    return found


def unsynced(prs: list[list[float]], known: set[int]) -> list[tuple[int, float]]:
    """(رقم، زمنُ الدمج) لكلّ طلبٍ لم يُذكر، الأقدمُ أوّلاً."""
    return sorted(((int(n), float(at)) for n, at in prs if int(n) not in known), key=lambda x: x[1])


def level(late: int) -> str:
    return contract.WARN if late else contract.OK


def collect(now: float | None = None) -> None:
    moment = time.time() if now is None else now
    merged = github.fetch(MERGED_PATH, reduce_merged)
    if merged is None:
        failed(PANEL, "github")
        return
    raw = merged.get("prs")
    prs: list[list[float]] = raw if isinstance(raw, list) else []
    missing = unsynced(prs, synced_numbers())
    mentioned = mentioned_numbers()
    note_only = sum(1 for number, _ in missing if number in mentioned)
    late = [item for item in missing if (moment - item[1]) / 3600 > GRACE_HOURS]
    total = len(prs)
    synced = total - len(missing)
    gauge: float | None
    if not total:
        headline, gauge = "لا طلباتٍ مدموجةً في العيّنة", None
    elif not missing:
        headline, gauge = "كلُّ المدموج مُزامَنٌ في حقل الطلب", 100
    else:
        headline = f"{len(missing)} طلباً دُمج ولم يُزامَن"
        gauge = 100 * synced / total
    oldest = "—" if not missing else f"منذ {int((moment - missing[0][1]) // 3600)} س"
    publish(
        PANEL,
        status=level(len(late)),
        headline=headline,
        gauge=gauge,
        metrics=(
            ("مدموجٌ لم يُزامَن", len(missing)),
            ("متأخّرٌ فوق 24 س", len(late)),
            ("أقدمُ غيرِ مُزامَن", oldest),
            ("مذكورٌ في ملاحظةٍ فقط", note_only),
            ("في العيّنة" + (" (محدودة)" if merged.get("full") else ""), total),
        ),
    )

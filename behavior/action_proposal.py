"""اقتراحُ الإجراء من سلّم المخالفات المعتمد (W-20261108-005).

مصدرُ الحقيقة: ``AAdocs/ministry_data/2026_2027/08_conduct_policy_2026.md`` م3.5.3 — سلّمُ الدرجة الأولى
(ص85–86) وجداولُ الدرجة الثانية (ص87 وما بعدها). تُقرأ الخطواتُ من ``conduct_2026.LADDERS`` المنقولةِ
من الدليل لا من الذاكرة. والدرجتان 3 و4 لم يُستخرج نصُّهما في الملفّ فلا يُقترح لهما شيءٌ آليّاً:
يكتب المنسّقُ الإجراءَ بنفسه عند الاعتماد. والاقتراحُ لا يصل أسرةً ولا يُشعَر به وليُّ الأمر.
"""

from __future__ import annotations

from dataclasses import dataclass

from .conduct_2026 import BY_CODE, PS, SW, SWPS

#: الدرجاتُ التي يُقترح لها آليّاً — ما استُخرج نصُّه فقط.
SUGGESTIBLE_DEGREES = frozenset({1, 2})

SOURCE_FILE = "AAdocs/ministry_data/2026_2027/08_conduct_policy_2026.md"
ARTICLE = "م3.5.3"

#: فاعلو الاختصاص: خطوةٌ يقع فيها أحدُهم تصل الاختصاصيَّين في قائمتهما ليدرسا الحالة.
_SPECIALIST_ACTORS = frozenset({SW, PS, SWPS})


@dataclass(frozen=True)
class Proposal:
    """اقتراحُ إجراءٍ: نصُّ الخطوة، ومصدرُه برقم المادة والصفحة، ورقمُ المرّة، وهل تصل الاختصاصيَّين."""

    text: str
    source: str
    step: int
    specialist: bool


def propose(code: str, step: int) -> Proposal | None:
    """الاقتراحُ للمخالفة ``code`` عند التكرار ``step`` — ``None`` إن لم يكن لها سلّمٌ مستخرجُ النصّ."""
    item = BY_CODE.get(code)
    if item is None or item.degree not in SUGGESTIBLE_DEGREES or step < 1:
        return None
    ladder = item.steps
    # ما بعد آخر مرّةٍ في السلّم إحالةٌ إلى قسم حماية ورعاية الطلبة — قرارٌ خارج هذا الاقتراح فلا يُخمَّن.
    if ladder.is_beyond(step):
        return None
    rows = ladder.step(step)
    return Proposal(
        text=" · ".join(f"{actor}: {action}" for actor, action in rows),
        source=f"{SOURCE_FILE} {ARTICLE} ص{ladder.pages} — المرّة {step}",
        step=step,
        specialist=any(actor in _SPECIALIST_ACTORS for actor, _ in rows),
    )

"""operations/schedule_decision.py — بطاقةُ قرار المسودّة في صفحة الجدولة (W-20261010-001، D-310م).

المصدرُ **لقطةُ V2** (`config_snapshot["evaluation"]`) التي كتبها المشغِّلُ بعد أن قبلها المُقيِّمُ المستقلّ،
لا إعادةُ حسابٍ في الطلب: فلا `ScheduleLab.compute()` هنا، ولا استعلامَ. والبطاقةُ بخمسة مؤشّراتٍ لا اثنين
وعشرين؛ وما لم يُقَس بعدُ يُقال «لم يُقَس» ولا يُملأ برقمٍ مخمَّن (ينتظر بطاقةَ المقارنة بالمعتمد W-20261009-008).

والأرقامُ الثلاثةُ للحكم (خروقٌ صلبة، حصصٌ بلا موضع، مجموعُ جزاءات المرنة) باسمٍ بشريّ ومعنى؛ أمّا
`InfeasibilityValue` فلا يُذكر باسمه التقنيّ (قرار 0101، 2026-10-10).
"""

from __future__ import annotations

from typing import Any

from .schedule_evaluator import VERDICTS

#: اسمُ المحرّك في لقطة التوليد — يطابق `scheduler_v2.runner.ENGINE` (غيابُه = توليدٌ من المحرّك السابق).
ENGINE = "cpsat_v2"

#: ما لم يُقَس بعدُ: يُذكر سببُه ولا يُخمَّن له رقم (قرار 0101، 2026-10-10).
_UNMEASURED = "لم يُقَس"
_PENDING_NOTE = "تنتظر بطاقةَ المقارنة بالمعتمد (W-20261009-008)"

#: حالةُ الحلّال بمعنى بشريّ: لماذا توقّف المولّد؟
_STOP_REASONS = {
    "OPTIMAL": "أثبت الحلّالُ أنّه لا أفضل منه",
    "FEASIBLE": "وجد حلاًّ وتوقّف قبل إثبات الأمثليّة (انتهت المهلة أو أُوقف مبكّراً)",
    "UNKNOWN": "انتهت المهلة بلا إثباتٍ — ضيقُ وقتٍ لا استحالة",
    "INFEASIBLE": "مستحيلٌ بالبرهان",
}


def is_v2(snapshot: dict | None) -> bool:
    """أصدرَ هذا التوليدَ محرّكُ V2؟ — الصفوفُ الأقدمُ بلا `engine` في لقطتها."""
    return (snapshot or {}).get("engine") == ENGINE


def evaluation_of(snapshot: dict | None) -> dict | None:
    """تقييمُ المُقيِّم المحفوظ في اللقطة — أو `None` لتوليدٍ سبقه أو فشل قبله."""
    recorded = (snapshot or {}).get("evaluation")
    return recorded if is_v2(snapshot) and isinstance(recorded, dict) else None


def stop_reason(snapshot: dict | None) -> str:
    """لماذا توقّف التوليد؟ — بمعنى بشريّ من حالة الحلّال لا من رمزها."""
    status = ((snapshot or {}).get("solver") or {}).get("status")
    return _STOP_REASONS.get(status, VERDICTS.get(status, "")) if status else ""


def declared_relaxations(snapshot: dict | None) -> dict:
    """التخفيفاتُ المعلَنة: لا تخفيفَ صامت — عددُ المعلّمين وما صار ملاحظةً بسببها."""
    recorded = ((snapshot or {}).get("relaxations") or {}).get("hc5_run_caps") or []
    eased = (evaluation_of(snapshot) or {}).get("eased") or {}
    return {
        "teachers": len(recorded),
        "eased": sum(eased.values()),
        "text": "حصّتان متتاليتان لا ثلاث" if recorded else "",
    }


def row_summary(snapshot: dict | None) -> dict | None:
    """سطرُ سجلّ التوليد لـV2: ما وُضع من المطلوب وحالةُ القبول — بلا تقييمٍ يُعاد."""
    ev = evaluation_of(snapshot)
    if ev is None:
        return None
    hard, unplaced = int(ev.get("hard_total") or 0), int(ev.get("InfeasibilityValue") or 0)
    if ev.get("accepted"):
        state, tone = "مقبولة", "success"
    else:
        state, tone = f"فيها {hard} خرقاً و{unplaced} حصّةً بلا موضع", "danger"
    return {
        "placed": ev.get("placed_periods"),
        "required": ev.get("required_periods"),
        "state": state,
        "tone": tone,
        "accepted": bool(ev.get("accepted")),
    }


def decision_card(snapshot: dict | None) -> dict | None:
    """بطاقةُ القرار: الحكمُ والأرقامُ الثلاثة والمؤشّراتُ الخمسة وسببُ التوقّف والتخفيفاتُ المعلَنة."""
    ev = evaluation_of(snapshot)
    if ev is None:
        return None
    soft: dict[str, Any] = ev.get("soft_counts") or {}
    eased = declared_relaxations(snapshot)
    hard, unplaced = int(ev.get("hard_total") or 0), int(ev.get("InfeasibilityValue") or 0)
    indicators = [
        {
            "code": "IND-02",
            "label": "اكتمال التموضع",
            "value": f"{ev.get('placed_periods')} من {ev.get('required_periods')}",
            "unit": "حصّة",
            "meaning": "كم حصّةً من المطلوبة وجدت موضعها في الأسبوع",
            "direction": "الأعلى أفضل",
            "cap": "السقف: كلُّ المطلوب",
            "measured": True,
        },
        {
            "code": "IND-04",
            "label": "فراغات المعلّمين",
            "value": _UNMEASURED,
            "unit": "نسبة أيّام المعلّمين",
            "meaning": "نسبةُ أيّام المعلّمين التي بين حصصهم فراغ",
            "direction": "الأقلّ أفضل",
            "cap": _PENDING_NOTE,
            "measured": False,
        },
        {
            "code": "IND-08",
            "label": "تجاوز التتابع",
            "value": str(int(soft.get("consecutive") or 0)),
            "unit": "حالة",
            "meaning": "مرّات وقوف المعلّم حصصاً متصلةً أكثرَ من الحدّ المرن",
            "direction": "الأقلّ أفضل",
            "cap": (
                f"يشمل {eased['eased']} من المواضع خُفِّف بقرارٍ معلَن"
                if eased["eased"]
                else "لا تخفيفَ معلَناً هنا"
            ),
            "measured": True,
        },
        {
            "code": "IND-13",
            "label": "عدالة الأطراف",
            "value": _UNMEASURED,
            "unit": "نسبة",
            "meaning": "أكثرُ معلّمٍ تحمّلاً للحصّة الأولى والأخيرة مقابل المتوسّط",
            "direction": "الأقلّ أفضل",
            "cap": _PENDING_NOTE,
            "measured": False,
        },
        {
            "code": "IND-16",
            "label": "تحقّق تفضيلات المعلّمين",
            "value": _UNMEASURED,
            "unit": "نسبة",
            "meaning": "نسبةُ ما طلبه المعلّمون كتابةً (كيوم التفريغ) ممّا تحقّق",
            "direction": "الأعلى أفضل",
            "cap": _PENDING_NOTE,
            "measured": False,
        },
    ]
    return {
        "accepted": bool(ev.get("accepted")),
        "verdict": (
            "مقبولةٌ للاعتماد: لا خرقَ صلباً ولا حصّةَ بلا موضع"
            if ev.get("accepted")
            else "لا تُعتمد بلا إقرار: فيها ما يمنع القبول"
        ),
        "hard": hard,
        "unplaced": unplaced,
        "objective": round(ev["ObjectiveValue"]) if ev.get("ObjectiveValue") is not None else None,
        "indicators": indicators,
        "stop_reason": stop_reason(snapshot),
        "relaxations": eased,
    }


def current_card(generations: list) -> tuple[Any, dict | None]:
    """أحدثُ مسودّةٍ من V2 وبطاقتُها — `(None, None)` إن لم تكن."""
    for g in generations:
        card = decision_card(g.config_snapshot) if g.status == "draft" else None
        if card:
            return g, card
    return None, None


def annotate_generation(g: Any, total_weekly: int, baseline: Any) -> None:
    """ما يحتاجه سطرُ السجلّ: ما وُضع، وسطرُ V2، ونسبةُ الأساس لتوليدات V2 وحدَها.

    المؤشّراتُ تُعاد من الحصص لا تُقرأ من الصفّ (المخزَّنُ كُتب بتعريفات يومه). لكنّ ذلك لتوليدات V2 فقط:
    حسابُ المختبر لكلّ صفٍّ هو أثقلُ ما في فتح الصفحة، وصفوفُ المحرّك السابق تُطوى بلا درجة.
    """
    from .schedule_lab import ScheduleLab, overall_score, relative_score

    g.placed = g.slot_rows or g.total_slots_created
    # نصٌّ لا رقم: `floatformat` يتبع اللغةَ فيكتب «100٫0»، والرقمُ هنا يُقرأ ويُقارَن.
    g.placed_ratio = f"{100 * g.placed / total_weekly:.1f}" if total_weekly else "0.0"
    g.v2 = row_summary(g.config_snapshot)
    lab = ScheduleLab.for_generation(g).compute() if g.v2 and g.placed else {}
    g.lab_absolute = overall_score(lab) if lab else None
    g.lab_relative = relative_score(lab, baseline.metrics) if baseline and lab else None


def split_generations(generations: list) -> tuple[list, list]:
    """`(الظاهر, المطويّ)` — صفوفُ المحرّك السابق المنتهيةُ تُطوى بلا أزرار، ولا يُحذف منها شيء.

    ومسودّةُ المحرّك السابق تبقى ظاهرةً بأزرارها: طيُّها يحجب اعتمادَها أو تجاهلَها.
    """
    folded = [g for g in generations if not g.v2 and g.status in ("approved", "archived", "failed")]
    return [g for g in generations if g not in folded], folded

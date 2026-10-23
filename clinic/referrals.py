"""
clinic/referrals.py — الإحالات وإيصالُها (W-20261020-038)
══════════════════════════════════════════════════════════
إحالةٌ واحدةٌ لكلّ زيارةٍ خرجت «بإحالة»، برقمٍ تسلسليٍّ لكلّ مدرسة، وجهةِ متابعةٍ من قائمةٍ ثابتة،
وإغلاقٍ يدويّ بتاريخٍ ونتيجةٍ من قائمةٍ ثابتة. والإيصالُ لا يحمل تشخيصاً ولا سبباً: اسمُ الطالب مخفيٌّ
جزئياً ورقمُ الإحالة وجهتُها وتاريخُها وحسب.
"""

from __future__ import annotations

from django.db import IntegrityError, transaction
from django.db.models import Max
from django.utils import timezone

from clinic import choices
from clinic.models import ClinicReferral, ClinicVisit


def mask_person_name(full_name: str) -> str:
    """يُبقي الاسمَ الأوّل ويستر ما بعده بحرفه الأوّل: «أحمد محمد علي» ← «أحمد م*** ع***»."""
    parts = (full_name or "").split()
    if not parts:
        return ""
    return " ".join([parts[0], *(f"{p[0]}***" for p in parts[1:])])


@transaction.atomic
def open_referral(visit: ClinicVisit, follow_up_party: str) -> ClinicReferral:
    """يفتح إحالةً للزيارة (مرّةً واحدة)، أو يُعيد القائمةَ إن وُجدت.

    Raises:
        ValueError: جهةُ متابعةٍ خارج القائمة
    """
    if not choices.is_valid_followup(follow_up_party):
        raise ValueError(f"جهة متابعة غير معتمدة: {follow_up_party}")
    existing = ClinicReferral.objects.filter(visit=visit).first()
    if existing:
        return existing
    for _ in range(3):  # تصادمٌ نادرٌ بين إحالتين متزامنتين على الرقم نفسه
        last = (
            ClinicReferral.objects.filter(school=visit.school).aggregate(m=Max("serial_no"))["m"]
            or 0
        )
        try:
            with transaction.atomic():
                return ClinicReferral.objects.create(
                    school=visit.school,
                    visit=visit,
                    serial_no=last + 1,
                    follow_up_party=follow_up_party,
                )
        except IntegrityError:
            continue
    raise ValueError("تعذّر إسناد رقم تسلسلي للإحالة")


@transaction.atomic
def close_referral(referral: ClinicReferral, result_code: str, by) -> ClinicReferral:
    """إغلاقٌ يدويٌّ بنتيجةٍ من القائمة.

    Raises:
        ValueError: نتيجةٌ خارج القائمة، أو إحالةٌ مغلقةٌ سلفاً
    """
    if not choices.is_valid_referral_result(result_code):
        raise ValueError(f"نتيجة غير معتمدة: {result_code}")
    if referral.status == choices.REFERRAL_CLOSED:
        raise ValueError("الإحالة مغلقة سلفاً")
    referral.status = choices.REFERRAL_CLOSED
    referral.result_code = result_code
    referral.closed_on = timezone.localdate()
    referral.closed_by = by
    referral.save(update_fields=["status", "result_code", "closed_on", "closed_by"])
    return referral

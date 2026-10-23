"""
clinic/choices.py — القوائم المغلقة لترميز زيارة العيادة (W-20261020-029)
════════════════════════════════════════════════════════════════════════
الخدماتُ (21 في 7 مجموعات) والشكاوى (12 منها «أخرى») معتمدةٌ مبدئيّاً بقرار المالك
2026-10-21 وتُعدَّل قيماً إن أرسل المالكُ الملفَّ المرجعيّ.

القيمُ تُخزَّن رموزاً ثابتةً (لا نصوصاً عربيّةً) في أعمدةٍ بلا `choices` على مستوى
الحقل، فتعديلُ قائمةٍ أو إضافةُ بندٍ **لا يولّد هجرةً**؛ والتحقّقُ من الرمز هنا
(`is_valid_service` وأخواتها) في الخدمة والنموذج. والرمزُ لا يُغيَّر بعد أن يُستعمل،
فالعرضُ العربيُّ وحدَه هو ما يُعدَّل.
"""

from __future__ import annotations

# ── المجموعات ────────────────────────────────────────────────────────
GROUP_FIRST_AID = "first_aid"
GROUP_MEDICATION = "medication"
GROUP_DIABETES = "diabetes"
GROUP_RESPIRATORY = "respiratory"
GROUP_VITALS = "vitals"
GROUP_REFERRAL = "referral"
GROUP_INFECTIOUS = "infectious"

SERVICE_GROUPS: tuple[tuple[str, str], ...] = (
    (GROUP_FIRST_AID, "إسعافات أوّليّة"),
    (GROUP_MEDICATION, "أدوية"),
    (GROUP_DIABETES, "السكّري"),
    (GROUP_RESPIRATORY, "التنفّس"),
    (GROUP_VITALS, "العلامات الحيويّة"),
    (GROUP_REFERRAL, "إحالات"),
    (GROUP_INFECTIOUS, "أمراض معدية"),
)

# (الرمز، العرض، المجموعة)
SERVICES: tuple[tuple[str, str, str], ...] = (
    ("bandage", "ضماد", GROUP_FIRST_AID),
    ("bandage_wrap", "رباط", GROUP_FIRST_AID),
    ("paracetamol_tablet", "باراسيتامول أقراص", GROUP_MEDICATION),
    ("paracetamol_syrup", "باراسيتامول شراب", GROUP_MEDICATION),
    ("ibuprofen_tablet", "إيبوبروفين أقراص", GROUP_MEDICATION),
    ("ibuprofen_syrup", "إيبوبروفين شراب", GROUP_MEDICATION),
    ("nasal_drops", "قطرة أنف", GROUP_MEDICATION),
    ("ors", "أملاح الإماهة الفموية", GROUP_MEDICATION),
    ("diclofenac_gel", "جل ديكلوفيناك", GROUP_MEDICATION),
    ("glucose_test", "فحص السكر", GROUP_DIABETES),
    ("insulin", "إنسولين", GROUP_DIABETES),
    ("urine_ketones", "كيتون البول", GROUP_DIABETES),
    ("salbutamol_inhaler", "بخّاخ فنتولين", GROUP_RESPIRATORY),
    ("nebulizer", "نيبولايزر", GROUP_RESPIRATORY),
    ("oxygen", "أكسجين", GROUP_RESPIRATORY),
    ("temperature", "قياس الحرارة", GROUP_VITALS),
    ("blood_pressure", "قياس الضغط", GROUP_VITALS),
    ("referral_health_center", "إحالة إلى المركز الصحّي", GROUP_REFERRAL),
    ("referral_specialist", "إحالة إلى عيادة متخصّصة", GROUP_REFERRAL),
    ("referral_emergency", "إحالة إلى الطوارئ", GROUP_REFERRAL),
    ("infectious_case", "حالة معدية مشتبه بها", GROUP_INFECTIOUS),
)

SERVICE_CHOICES: tuple[tuple[str, str], ...] = tuple((code, label) for code, label, _g in SERVICES)
_GROUP_OF_SERVICE: dict[str, str] = {code: group for code, _label, group in SERVICES}

# ── الشكاوى (12، آخرها «أخرى») ───────────────────────────────────────
COMPLAINT_OTHER = "other"
COMPLAINT_CHOICES: tuple[tuple[str, str], ...] = (
    ("headache", "صداع"),
    ("abdominal_pain", "ألم في البطن"),
    ("fever", "حرارة مرتفعة"),
    ("nausea_vomiting", "غثيان أو قيء"),
    ("dizziness", "دوار أو إغماء"),
    ("injury", "إصابة أو رضّ"),
    ("nosebleed", "رعاف"),
    ("cough_breathing", "سعال أو ضيق تنفّس"),
    ("throat_ear", "ألم حلق أو أذن"),
    ("allergy_rash", "حساسية أو طفح"),
    ("eye_problem", "مشكلة في العين"),
    (COMPLAINT_OTHER, "أخرى"),
)

# ── حالة الخروج من العيادة ───────────────────────────────────────────
OUTCOME_RETURN = "return_to_class"
OUTCOME_LEAVE = "sent_home"
OUTCOME_REFERRAL = "referral"
OUTCOME_CHOICES: tuple[tuple[str, str], ...] = (
    (OUTCOME_RETURN, "عودة إلى الصف"),
    (OUTCOME_LEAVE, "استئذان"),
    (OUTCOME_REFERRAL, "إحالة"),
)


# ── الإحالات (W-20261020-038) ────────────────────────────────────────
#: جهةُ المتابعة وحالةُ الإحالة ونتيجةُ إغلاقها رموزٌ ثابتة؛ لا نصَّ حرّاً ولا تشخيصَ فيها.
FOLLOWUP_CHOICES: tuple[tuple[str, str], ...] = (
    ("health_center", "المركز الصحي"),
    ("hospital", "المستشفى"),
    ("parent", "ولي الأمر"),
    ("counselor", "المرشد الاجتماعي"),
)
REFERRAL_OPEN = "open"
REFERRAL_CLOSED = "closed"
REFERRAL_RESULT_CHOICES: tuple[tuple[str, str], ...] = (
    ("treated", "تمّت المعالجة"),
    ("follow_up_scheduled", "حُدّد موعد متابعة"),
    ("no_show", "لم يراجع"),
    ("transferred", "حُوّل إلى جهة أخرى"),
)


def is_valid_followup(code: str) -> bool:
    return any(code == c for c, _ in FOLLOWUP_CHOICES)


def is_valid_referral_result(code: str) -> bool:
    return any(code == c for c, _ in REFERRAL_RESULT_CHOICES)


#: يضعها الإغلاقُ التلقائيّ وحده بعد انقضاء المهلة؛ لا تُعرض للممرّض ولا يقبلها `is_valid_outcome`.
OUTCOME_AUTO = "auto_closed"
#: ساعاتُ الزيارة المفتوحة قبل أن تُغلق آلياً (قرار المالك 2026-10-20).
AUTO_CLOSE_HOURS = 3

STATE_WAITING = "waiting"
STATE_IN_CARE = "in_care"
STATE_DONE = "done"


def group_of_service(code: str) -> str:
    """مجموعةُ الخدمة، أو سلسلةٌ فارغة لرمزٍ غير معتمد."""
    return _GROUP_OF_SERVICE.get(code, "")


def is_valid_service(code: str) -> bool:
    return code in _GROUP_OF_SERVICE


def is_valid_complaint(code: str) -> bool:
    return any(code == c for c, _ in COMPLAINT_CHOICES)


def is_valid_outcome(code: str) -> bool:
    return any(code == c for c, _ in OUTCOME_CHOICES)

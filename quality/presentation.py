"""ألوانُ العرض في وحدة الجودة — تُحسب هنا لا في القوالب.

كانت كلُّ صفحةٍ تكتب عتباتِها في سلسلة `{% if %}`، فاختلفت العتباتُ بين
صفحتين تعرضان الرقمَ نفسَه، وأعاد فرعُ «30% فأقلّ» في تقرير التقدّم لونَ
«فوق 60%» نفسَه، وقارنت شارةُ الحالة بمفاتيحَ لا وجودَ لها.
"""

from __future__ import annotations

#: شارةُ حالة الإجراء — لاحقةُ `status-badge status-…`.
PROCEDURE_STATUS_TONE = {
    "Completed": "success",
    "In Progress": "warning",
    "Pending Review": "info",
    "Cancelled": "gray",
    "Not Started": "gray",
}


def procedure_status_tone(status: str) -> str:
    return PROCEDURE_STATUS_TONE.get(status, "gray")


def progress_tone(pct: int | float | None, total: int | None = None) -> str:
    """لونُ نسبة الإنجاز — رمزُ بطاقة الرقم، وهو اسمُ صنف القوس أيضاً.

    العتباتُ واحدةٌ في اللوحة وتقرير التقدّم والمجال: 100% أخضر، وفوق 60% عنّابيّ،
    وفوق 30% سماويّ، وما دونها كهرمانيّ. كانت في القوالب ثلاثَ مجموعات
    (60/30 و50/25 و60 وحدها)، وفي تقرير التقدّم كان ما دون 30% يعود عنّابيّاً
    كأنّه فوق 60%. ولا إجراءاتٍ أصلاً → `muted` (لا نسبةَ تُحكم).
    """
    if total == 0 or pct is None:
        return "muted"
    if pct >= 100:
        return "green"
    if pct > 60:
        return "maroon"
    if pct > 30:
        return "sky"
    return "amber"


def kpi_progress_tone(pct: int | float | None, total: int | None = None) -> str:
    """كـ`progress_tone` لكن لبطاقة الرقم، ولا رماديَّ فيها — فالفارغُ عنّابيّ."""
    tone = progress_tone(pct, total)
    return "maroon" if tone == "muted" else tone


#: حالةُ تقييم الموظف — لاحقةُ `status-badge status-…` (كما كانت في القالب ثلاثَ مرّات).
EVALUATION_STATUS_TONE = {
    "acknowledged": "success",
    "approved": "info",
    "submitted": "warning",
    "draft": "gray",
}


def evaluation_status_tone(status: str) -> str:
    return EVALUATION_STATUS_TONE.get(status, "gray")


def evaluation_rating_tone(rating: str) -> str:
    """لونُ الدرجة: ممتازٌ أخضر، ويحتاج تطويراً أحمر، وما بينهما كهرمانيّ — كما كان."""
    if rating == "excellent":
        return "success"
    if rating == "needs_dev":
        return "danger"
    return "warning"


#: مسؤوليّةُ عضو اللجنة — كان الرئيسُ يُرسم بلون الخطر (`q-badge-danger`)،
#: وليست الرئاسةُ خطراً: صار عنّابيَّ الهويّة.
RESPONSIBILITY_TONE = {
    "رئيس اللجنة": "maroon",
    "نائب رئيس اللجنة": "warning",
    "مقرر": "info",
}


def responsibility_tone(responsibility: str) -> str:
    return RESPONSIBILITY_TONE.get(responsibility, "gray")


def bar_tone(pct: int | float, green_at: int = 70, amber_at: int = 40) -> str:
    """لونُ شريط تقدّمٍ صغير: أخضر/كهرمانيّ/أحمر — بعتبات القالب الذي جاء منه."""
    if pct >= green_at:
        return "green"
    if pct >= amber_at:
        return "amber"
    return "red"


# ── الزيارات الصفّيّة ─────────────────────────────────────────────────────

#: نوعُ الزيارة — لاحقةُ `badge badge--…`. كان الأرشيفُ يعرض زيارةَ الزميل «إشرافيّة».
OBSERVATION_KIND_TONE = {"self": "accent", "peer": "success", "supervision": "info"}

#: حالةُ الزيارة — لاحقةُ `badge badge--…`.
OBSERVATION_STATUS_TONE = {"acknowledged": "success", "submitted": "warning", "draft": "neutral"}


def observation_score_tone(score) -> str:
    """لونُ النسبة الإجماليّة — العتبةُ كما كانت في القالب: 75 فأكثر، ثمّ 50 فأكثر."""
    if score is None:
        return "muted"
    if score >= 75:
        return "success"
    if score >= 50:
        return "warning"
    return "danger"


def decorate_observation(obs) -> None:
    """يُلحق بالزيارة ألوانَ عرضها — نوعها وحالتها ونسبتها."""
    obs.kind_tone = OBSERVATION_KIND_TONE.get(obs.kind, "info")
    obs.status_tone = OBSERVATION_STATUS_TONE.get(obs.status, "neutral")
    obs.score_tone = observation_score_tone(obs.score_percent)

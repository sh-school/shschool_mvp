"""ألوانُ العرض في وحدة الجودة — تُحسب هنا لا في القوالب.

كانت كلُّ صفحةٍ تكتب عتباتِها في سلسلة `{% if %}`، فاختلفت العتباتُ بين
صفحتين تعرضان الرقمَ نفسَه، وأعاد فرعُ «30% فأقلّ» في تقرير التقدّم لونَ
«فوق 60%» نفسَه، وقارنت شارةُ الحالة بمفاتيحَ لا وجودَ لها.
"""

from __future__ import annotations

from core.domain.tones import tone_for

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
    """لونُ المستوى: ممتازٌ أخضر، وضعيفٌ أحمر، وما بينهما (جيد جداً، جيد، مقبول) كهرمانيّ."""
    if rating == "excellent":
        return "success"
    if rating == "weak":
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
    return tone_for(pct, ((green_at, "green"), (amber_at, "amber"), (None, "red")))


# ── الزيارات الصفّيّة ─────────────────────────────────────────────────────

#: نوعُ الزيارة — لاحقةُ `badge badge--…`. كان الأرشيفُ يعرض زيارةَ الزميل «إشرافيّة».
OBSERVATION_KIND_TONE = {"self": "accent", "peer": "success", "supervision": "info"}

#: حالةُ الزيارة — لاحقةُ `badge badge--…`.
OBSERVATION_STATUS_TONE = {"acknowledged": "success", "submitted": "warning", "draft": "neutral"}


#: لونُ النسبة الإجماليّة للزيارة: 75 فأكثر نجاح، و50 فأكثر تحذير، ودونها خطر.
OBSERVATION_SCORE_TONES = ((75, "success"), (50, "warning"), (None, "danger"))


def observation_score_tone(score: int | float | None) -> str:
    """لونُ النسبة الإجماليّة — وما لم يُحسب رماديّ."""
    return tone_for(score, OBSERVATION_SCORE_TONES)


def decorate_observation(obs) -> None:
    """يُلحق بالزيارة ألوانَ عرضها — نوعها وحالتها ونسبتها."""
    obs.kind_tone = OBSERVATION_KIND_TONE.get(obs.kind, "info")
    obs.status_tone = OBSERVATION_STATUS_TONE.get(obs.status, "neutral")
    obs.score_tone = observation_score_tone(obs.score_percent)


#: الحالاتُ التي بعد الإرسال: توقيعُ الزائر يُختم فيها وحدَها. المسودّةُ لا ختمَ عليها، والمسحوبةُ مسودّةٌ (السحبُ يعيدها
#: إلى `draft` ويمحو الوقتَين) — فالحالةُ هي الحكمُ لا الوقتُ وحدَه؛ وقتٌ عالقٌ على مسودّةٍ لا يُختم.
_SIGNED_BY_VISITOR = ("submitted", "acknowledged")


def _stamp(user, moment) -> dict[str, str] | None:
    """{الاسم، الوقت بتوقيت الدوحة} أو None إن غاب أحدُهما — ختمٌ بلا اسمٍ أو وقتٍ ليس توقيعاً."""
    from django.utils import timezone

    name = (getattr(user, "full_name", "") or "").strip()
    if not name or moment is None:
        return None
    local = timezone.localtime(moment, timezone.get_default_timezone())
    return {"name": name, "at": local.strftime("%Y/%m/%d %H:%M")}


def signature_stamps(obs) -> dict[str, dict[str, str] | None]:
    """ختمُ «توقيعٌ إلكترونيّ داخل المنصّة» في خانتَي التوقيع من PDF استمارة الزيارة الصفّيّة (F55E).

    الزائرُ: يُختم بعد الإرسال باسمه ووقت **آخرِ** إرسالٍ (`submitted_at` يتجدّد مع كلّ إرسال). والمعلّمُ: بعد اطّلاعه
    باسمه ووقت اطّلاعه. فإن لم يُرسَل أو لم يطّلع بقيت الخانةُ فارغةً للتوقيع اليدويّ. **الأسماءُ وحدَها** — لا رقمَ
    وظيفيّاً ولا هويّةً — والوقتُ بتوقيت الدوحة أيّاً كان المنطقةُ الزمنيّةُ النشطة (كسائر وثائق PDF).
    """
    visitor = _stamp(obs.observer, obs.submitted_at) if obs.status in _SIGNED_BY_VISITOR else None
    teacher = (
        _stamp(obs.teacher, obs.teacher_acknowledged_at) if obs.status == "acknowledged" else None
    )
    return {"visitor": visitor, "teacher": teacher}


#: لونُ مرحلة التظلّم (المادة 20): ما ينتظر أحداً كهرمانيّ، والنهائيُّ أخضر، والرفضُ الحكميّ أحمر.
GRIEVANCE_STAGE_TONE = {
    "unknown": "gray",
    "open": "warning",
    "filed": "warning",
    "decided": "warning",
    "approved": "success",
    "closed": "success",
    "lapsed": "danger",
}


def grievance_stage_tone(code: str) -> str:
    return GRIEVANCE_STAGE_TONE.get(code, "gray")

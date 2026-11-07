"""سياسةُ اتّجاه الورق والإطار لوثائق الطباعة — المصدرُ الواحد (W-20261021-007، قرارُ المالك 2026-10-21).

القاعدة: **أفقيٌّ للقوائم والكشوف، وعموديٌّ للنماذج والخطابات**؛ والشعارُ إلزاميٌّ في الوثائق الإداريّة، واستمارةُ الإشراف خارج
الإطار عمداً، ولا خانةَ ختمٍ في أيّ وثيقة (قرارُ المالك 2026-11-07؛ يحرسه `tests/test_print_policy.py`).

الجدولُ هنا يصنّف كلَّ قالبٍ مطبوعٍ ويصرّح بحاله (مطابقٌ / استثناءٌ بقرار / ديْنٌ مسجَّل)؛ ويحرسه `tests/test_print_policy.py`:
ملفٌّ جديدٌ يلزمه سطرٌ هنا، والدَّينُ لا يزيد.
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass

SHEET = "sheet"  # قائمةٌ أو كشفٌ: أعمدةٌ كثيرة
FORM = "form"  # نموذجٌ أو استمارةٌ أو شهادة
LETTER = "letter"  # خطابٌ أو تقريرٌ نصّيّ

KIND_ORIENT = {SHEET: "landscape", FORM: "portrait", LETTER: "portrait"}

# ── اتجاهُ الورق المختار من شريط التصدير الموحَّد (W-20261107-021، قرار المالك 2026-11-07) ──
# القاعدة: كلُّ تصديرٍ (PDF وExcel) يمرّ على `{% export_group %}` فيحمل قائمةَ «أفقي/رأسي» ثم Excel ثم PDF؛ والاختيارُ يصل
# الخادمَ معاملاً `orient=landscape|portrait` فيطبّقه `core/pdf_utils.py` (حجمُ @page) و`core/export_utils.py` (page_setup)؛
# وقيمةٌ مجهولةٌ تُهمل فيبقى الافتراضيُّ أي اتجاهُ المستند في الجدول أدناه.
ORIENT_PARAM = "orient"
ORIENT_CHOICES = {"landscape": "أفقي", "portrait": "رأسي"}


def clean_orient(value: object) -> str | None:
    """القيمةُ المعتمدةُ أو `None` — المجهولةُ تُهمل ولا تُرفع (الافتراضيُّ يحكم)."""
    text = str(value or "").strip().lower()
    return text if text in ORIENT_CHOICES else None


#: اتجاهُ الطلب الجاري (يضبطه وسيطُ `ExportOrientMiddleware` ومشغّلُ مهامّ التصدير الخلفيّة).
_requested: ContextVar[str | None] = ContextVar("requested_orient", default=None)


def requested_orient() -> str | None:
    return _requested.get()


@contextmanager
def use_orient(value: object) -> Iterator[None]:
    """يجعل اتجاهَ الطلب `value` (بعد التنقية) طوال الكتلة ثم يعيد ما كان."""
    token = _requested.set(clean_orient(value))
    try:
        yield
    finally:
        _requested.reset(token)


def orient_from(params: Mapping[str, str] | None) -> str | None:
    """الاتجاهُ من معاملات طلبٍ (`request.GET`/`POST` أو QueryDict المهمّة الخلفيّة)."""
    return clean_orient(params.get(ORIENT_PARAM)) if params else None


def default_orient(kind: str = SHEET, doc: str = "") -> str:
    """افتراضيُّ القائمة: اتجاهُ المستند `doc` في الجدول إن سُمّي، وإلا اتجاهُ نوعه (كشفٌ أفقيّ، نموذجٌ وخطابٌ رأسيّ)."""
    if doc:
        return DOCUMENTS[doc].default_orient
    return KIND_ORIENT[kind]


CONFORMS = "conforms"
EXCEPTION = "exception"  # يخالف الجدولَ بقرارٍ مسمّى من المالك
DEBT = "debt"  # يخالف ولم يُرحَّل بعد

#: الشعار: `base` يرثه من `reports/base_qatar_report.html`، `frame` من الإطار المركزيّ، `tag` وسمٌ مباشر، `outside` استمارةٌ خارج الإطار،
#: `missing` ديْنٌ (الترويسةُ نصّيّةٌ محقونة بلا شعار).
LOGO_BASE, LOGO_FRAME, LOGO_TAG, LOGO_OUTSIDE, LOGO_MISSING = (
    "base",
    "frame",
    "tag",
    "outside",
    "missing",
)


@dataclass(frozen=True)
class PrintDocument:
    kind: str
    default_orient: str  # الاتّجاهُ الافتراضيّ الفعليّ اليوم
    status: str
    logo: str
    note: str = ""

    @property
    def expected_orient(self) -> str:
        return KIND_ORIENT[self.kind]


DOCUMENTS: dict[str, PrintDocument] = {
    "templates/wings/register_pdf.html": PrintDocument(SHEET, "landscape", CONFORMS, LOGO_BASE),
    "templates/wings/ministry_pdf.html": PrintDocument(SHEET, "landscape", CONFORMS, LOGO_BASE),
    "templates/operations/absence_followup_print.html": PrintDocument(
        SHEET,
        "landscape",
        CONFORMS,
        LOGO_BASE,
        "صفحتا «التواصل» و«الإجراءات» أفقيّتان (قرار المالك D-449م، ينسخ قرار 2026-10-17).",
    ),
    "templates/breach/pdf_report.html": PrintDocument(LETTER, "portrait", CONFORMS, LOGO_BASE),
    "templates/quality/pdf/progress_report.html": PrintDocument(
        LETTER, "portrait", CONFORMS, LOGO_BASE
    ),
    "templates/reports/student_result_pdf.html": PrintDocument(
        FORM, "portrait", CONFORMS, LOGO_BASE
    ),
    "templates/student_affairs/student_profile_pdf.html": PrintDocument(
        FORM, "portrait", CONFORMS, LOGO_BASE
    ),
    "templates/student_affairs/student_list_pdf.html": PrintDocument(
        SHEET, "landscape", CONFORMS, LOGO_BASE
    ),
    "templates/student_affairs/attendance_overview_pdf.html": PrintDocument(
        SHEET, "landscape", CONFORMS, LOGO_BASE
    ),
    "templates/student_affairs/behavior_overview_pdf.html": PrintDocument(
        SHEET, "landscape", CONFORMS, LOGO_BASE
    ),
    "templates/student_affairs/tardiness_pdf.html": PrintDocument(
        SHEET, "landscape", CONFORMS, LOGO_BASE
    ),
    "templates/behavior/daily_report_pdf.html": PrintDocument(
        SHEET, "landscape", CONFORMS, LOGO_BASE
    ),
    "templates/behavior/statistics_pdf.html": PrintDocument(
        LETTER, "portrait", CONFORMS, LOGO_BASE
    ),
    "templates/schedule/print_schedule.html": PrintDocument(
        SHEET, "landscape", CONFORMS, LOGO_FRAME
    ),
    "templates/schedule/print_pages.html": PrintDocument(SHEET, "landscape", CONFORMS, LOGO_FRAME),
    "templates/behavior/pdf/base_form.html": PrintDocument(FORM, "portrait", CONFORMS, LOGO_FRAME),
    "templates/wings/pdf/exit_permit.html": PrintDocument(
        FORM,
        "portrait",
        CONFORMS,
        LOGO_BASE,
        "إذنُ خروج بورقة A5 عموديّة (@page في القالب)؛ يُبنى بـ`wings/exit_permit_pdf_services.py`.",
    ),
    "templates/quality/observation_pdf.html": PrintDocument(
        FORM,
        "portrait",
        CONFORMS,
        LOGO_OUTSIDE,
        "استمارةُ الإشراف خارج الإطار عمداً (قرار المالك 2026-10-21)",
    ),
}


def debt() -> list[str]:
    """القوالبُ المخالفةُ للاتّجاه أو الشعار ولم تُرحَّل (سقّاطة: لا تزيد)."""
    return sorted(
        path
        for path, d in DOCUMENTS.items()
        if d.status == DEBT or d.logo == LOGO_MISSING or d.default_orient != d.expected_orient
    )

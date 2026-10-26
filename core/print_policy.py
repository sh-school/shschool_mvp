"""سياسةُ اتّجاه الورق والإطار لوثائق الطباعة — المصدرُ الواحد (W-20261021-007، قرارُ المالك 2026-10-21).

القاعدة: **أفقيٌّ للقوائم والكشوف، وعموديٌّ للنماذج والخطابات**؛ والشعارُ إلزاميٌّ في الوثائق الإداريّة، واستمارةُ الإشراف خارج
الإطار عمداً، والختمُ خانةٌ يدويّةٌ فارغةٌ (`components/print/stamp_box.html`).

الجدولُ هنا يصنّف كلَّ قالبٍ مطبوعٍ ويصرّح بحاله (مطابقٌ / استثناءٌ بقرار / ديْنٌ مسجَّل)؛ ويحرسه `tests/test_print_policy.py`:
ملفٌّ جديدٌ يلزمه سطرٌ هنا، والدَّينُ لا يزيد.
"""

from __future__ import annotations

from dataclasses import dataclass

SHEET = "sheet"  # قائمةٌ أو كشفٌ: أعمدةٌ كثيرة
FORM = "form"  # نموذجٌ أو استمارةٌ أو شهادة
LETTER = "letter"  # خطابٌ أو تقريرٌ نصّيّ

KIND_ORIENT = {SHEET: "landscape", FORM: "portrait", LETTER: "portrait"}

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
    "templates/schedule/print_schedule.html": PrintDocument(
        SHEET, "landscape", CONFORMS, LOGO_FRAME
    ),
    "templates/schedule/print_pages.html": PrintDocument(SHEET, "landscape", CONFORMS, LOGO_FRAME),
    "templates/behavior/pdf/base_form.html": PrintDocument(FORM, "portrait", CONFORMS, LOGO_FRAME),
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

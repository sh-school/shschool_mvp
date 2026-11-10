"""حارسُ عقد التصدير المركزيّ (W-20261109-013): كلُّ `export_button` إمّا نوعٌ مسجَّلٌ في السجلّ المركزيّ أو مستثنًى بسببٍ مكتوب.

المفتاحُ: اسمُ المسار حين يُمرَّر (`"student_affairs:student_list_xlsx"`)، وإلّا `قالب::href|form` للزرّ بلا اسم مسار
(`href="?export=pdf"` أو زرِّ إرسالٍ في نموذج). وبطاقةُ الترحيل تنقل مفتاحَها من `EXEMPT` إلى `REGISTERED` — فلا يعود الاستثناءُ
يتّسع بصمت: زرٌّ جديدٌ بلا نوعٍ ولا سببٍ يُرفض، واستثناءٌ لم يعد لازماً يُرفض كذلك.
"""

import pathlib
import re

from core.exports import contract, registry

ROOT = pathlib.Path(__file__).resolve().parent.parent
_BUTTON = re.compile(r'\{% export_button "(?:xlsx|pdf)"(?:\s+"([^"]+)")?')

#: اسمُ المسار ← نوعُه في السجلّ المركزيّ (`core.exports.registry`) وعقدِ الجداول (`core.exports.contract`).
REGISTERED = {
    "student_affairs:student_list_xlsx": "student_affairs.student_list_xlsx",
    # W-20261109-006: الحضورُ والسلوكُ والتأخّرُ والأنشطةُ والتحرّكاتُ والتقريرُ اليوميّ والإحصاءُ وملفُّ الطالب.
    "student_affairs:attendance_export": "student_affairs.attendance_xlsx",
    "student_affairs:behavior_export": "student_affairs.behavior_xlsx",
    "student_affairs:tardiness_export": "student_affairs.tardiness_xlsx",
    "student_affairs:activities_export": "student_affairs.activities_xlsx",
    "student_affairs:enrolment_movements_export": "student_affairs.movements_xlsx",
    "behavior:daily_report_xlsx": "behavior.daily_xlsx",
    "templates/behavior/statistics.html::href": "behavior.statistics_xlsx",
    "behavior:student_profile_xlsx": "behavior.student_profile_xlsx",
}

_LATER = (
    "ترحيلٌ مؤجَّل: صفحةُ جدولٍ تُرحَّل إلى عقد core/exports في بطاقةٍ لاحقة "
    "(W-20261109-013 تبني العقدَ ونوعاً تجريبيّاً واحداً فقط)"
)
_SAME_TABLE = "PDF للجدول المسجَّل نفسِه: يبنيه `build_table_pdf` من `table_rows` بمحدِّد الجدول، فنوعُه ثانويٌّ لا جدولٌ مستقلّ"
_DOCUMENT = (
    "وثيقةٌ مفردةٌ لطالبٍ أو واقعة (كشفٌ/إنذارٌ/تعهّدٌ/استمارة) لا جدولٌ بصفوفٍ ومرشِّحات، فلا محدِّدَ قائمةٍ لها"
)
_BLANK = "قالبٌ فارغٌ للاستيراد (ترويسةُ أعمدةٍ بلا صفوف) لا تصديرُ بياناتٍ معروضة"

EXEMPT: dict[str, str] = {
    **dict.fromkeys(
        (
            "student_export_excel",
            "staff_affairs:attendance_report_xlsx",
            "staff_affairs:attendance_daily_xlsx",
            "schedule_export_excel",
            "schedule_export_pdf",
            "schedule_pages_pdf",
            "export_gradebook",
            "class_results_excel",
            "behavior_excel",
            "attendance_excel",
            "absence_followup_xlsx",
            "absence_followup_pdf",
            "quality_report_pdf",
            "kpi_monthly_pdf",
            "templates/wings/partials/record_panel.html::form",
            "templates/wings/ministry_report.html::form",
            "templates/reports/report_viewer.html::href",
            "templates/academic_management/reports/_base.html::href",
            "templates/operations/absence_followup/viewer.html::href",
        ),
        _LATER,
    ),
    **dict.fromkeys(
        (
            "student_affairs:student_list_pdf",
            "student_affairs:attendance_pdf",
            "student_affairs:behavior_pdf",
            "student_affairs:tardiness_pdf",
            "behavior:daily_report_pdf",
        ),
        _SAME_TABLE,
    ),
    **dict.fromkeys(
        (
            "wings:exit_permit_pdf",
            "student_result_pdf",
            "student_affairs:student_profile_pdf",
            "observation_pdf_view",
            "observation_pdf",
            "breach:pdf",
            "behavior:warning_pdf",
            "behavior:student_pdf",
            "behavior:student_behavior_pdf",
            "behavior:policy_pdf",
            "behavior:parent_pdf",
        ),
        _DOCUMENT,
    ),
    **dict.fromkeys(("student_import_template", "download_grade_template"), _BLANK),
}


def _buttons() -> set[str]:
    found: set[str] = set()
    templates = ROOT / "templates"
    for path in templates.rglob("*.html"):
        rel = "templates/" + path.relative_to(templates).as_posix()
        text = path.read_text(encoding="utf-8")
        for match in _BUTTON.finditer(text):
            if match.group(1):
                found.add(match.group(1))
                continue
            tail = text[match.end() : text.find("%}", match.end())]
            found.add(f"{rel}::{'form' if 'name=' in tail else 'href'}")
    return found


def test_every_export_button_is_registered_or_exempt_with_a_reason():
    unknown = sorted(_buttons() - set(REGISTERED) - set(EXEMPT))
    assert not unknown, (
        "زرُّ تصديرٍ بلا نوعٍ مسجَّلٍ في core/exports ولا استثناءٍ بسببه — سجّله بـ"
        f"contract.register_table أو أضفه إلى EXEMPT بسببٍ مكتوب: {unknown}"
    )


def test_no_stale_exemption_remains():
    stale = sorted(set(EXEMPT) - _buttons())
    assert not stale, f"استثناءٌ لم يعد له زرٌّ — احذفه من EXEMPT: {stale}"


def test_a_registered_button_is_not_also_exempt_and_exists():
    assert not set(REGISTERED) & set(EXEMPT)
    assert set(REGISTERED) <= _buttons(), "نوعٌ مسجَّلٌ بلا زرٍّ يستعمله في القوالب"


def test_every_exemption_carries_a_written_reason():
    assert all(reason.strip() for reason in EXEMPT.values())


def test_every_registered_button_kind_is_in_the_central_registry_and_the_contract():
    for url_name, kind in REGISTERED.items():
        assert registry.get(kind) is not None, f"{url_name}: النوعُ {kind} غيرُ مسجَّلٍ في السجلّ المركزيّ"
        assert kind in contract.tables(), f"{url_name}: النوعُ {kind} خارج عقد الجداول"

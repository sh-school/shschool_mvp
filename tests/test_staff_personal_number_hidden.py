"""[PII-UI] الرقمُ الشخصيّ للموظف لا يظهر في واجهة المنصّة (W-20261011-013، قرار المالك D-386م).

إخفاءٌ كاملٌ لا جزئيّ (بلا `mask_id`): الموظفُ يُستعلم عنه بالاسم والرقم الوظيفيّ وحدَهما. والحارسُ نصّيٌّ
بلا قاعدةٍ ولا خادم، يقرأ القوالبَ التي كانت تعرضه فيسقط إن عادت إليها أيُّ إشارةٍ إلى الحقل أو تسميتُه.
الاستعلامُ الخلفيّ والنماذجُ لم تتغيّر (الإخفاءُ في الواجهة فقط لحين تقرير الخلفيّة).
"""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TEMPLATES = ROOT / "templates"

#: قوالبُ تعرض موظفين: شؤون الموظفين كلُّها، ولجنةُ الجودة وربطُ المنفّذين، وإعادةُ كلمة المرور، وورقةُ الاعتماد.
GUARDED = (
    *sorted((TEMPLATES / "staff_affairs").rglob("*.html")),
    TEMPLATES / "quality" / "committee.html",
    TEMPLATES / "quality" / "executor_mapping.html",
    TEMPLATES / "core" / "it_admin" / "password_reset.html",
    TEMPLATES / "components" / "credentials_sheet.html",
)

#: إشاراتٌ إلى الحقل في أيّ صيغة: `national_id` و`.nid` و`mask_id` والتسميةُ الظاهرة.
FORBIDDEN = {
    "national_id": re.compile(r"national_id"),
    "nid": re.compile(r"\bnid\b"),
    "mask_id": re.compile(r"mask_id"),
    "تسميةُ الرقم الشخصي": re.compile(r"الرقم\s+الشخصي|رقم\s+شخصي"),
}


def _violations():
    out = []
    for path in GUARDED:
        text = path.read_text(encoding="utf-8")
        for name, pattern in FORBIDDEN.items():
            for match in pattern.finditer(text):
                line = text.count("\n", 0, match.start()) + 1
                out.append(f"{path.relative_to(ROOT).as_posix()}:{line}: {name}")
    return out


def test_the_guarded_templates_exist():
    missing = [p.relative_to(ROOT).as_posix() for p in GUARDED if not p.exists()]
    assert not missing, f"قوالبُ محروسةٌ غابت: {missing}"
    assert len(GUARDED) >= 8, "قائمةُ شؤون الموظفين اختفت من الحراسة"


def test_no_staff_personal_number_is_shown_in_the_guarded_templates():
    found = _violations()
    assert not found, (
        "الرقمُ الشخصيّ للموظف عاد إلى الواجهة (D-386م) — استعمل `employee_number` (الرقم الوظيفيّ):\n  "
        + "\n  ".join(found)
    )


def test_the_staff_search_is_announced_by_name_or_employee_number():
    staff_list = (TEMPLATES / "staff_affairs" / "staff_list.html").read_text(encoding="utf-8")
    reset = (TEMPLATES / "core" / "it_admin" / "password_reset.html").read_text(encoding="utf-8")
    assert 'placeholder="الاسم أو الرقم الوظيفي"' in staff_list
    assert '"الاسم أو الرقم الوظيفي"' in reset

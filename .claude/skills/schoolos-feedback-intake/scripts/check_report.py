#!/usr/bin/env python3
"""مدقّقُ تقرير «0201 · أمين البلاغات» اليوميّ قبل عرضه على المالك.

يفحص أمرين لا يُترك أيٌّ منهما للذاكرة:
  1) البنية: الأقسامُ الثلاثة، وأعمدةُ الجدول الثلاثة عشر بترتيب القالب، وقيمُ الأعمدة المغلقة
     (النوع، الأولويّة P0..P3، تقديرُ المدّة S/M/L/XL، صيغةُ التذكرة SOS-YYYYMMDD-XXXX).
  2) التسرّب: بريدٌ أو رابطٌ بمضيف أو رقمٌ طويلٌ أو هاتفٌ مجزّأ أو «لقب/ اسم» — أخطاءٌ تمنع العرض؛
     و«لقب + كلمة» واسمٌ لاتينيّ واقتباسٌ طويل — تنبيهاتٌ يراجعها الكاتبُ بعينه.

الاستعمال:
  python check_report.py report.md [--new-count N]
رمزُ الخروج: 0 نجاح (وقد تُطبع تنبيهات)، 1 أخطاء، 2 خطأُ استعمال.
لا يقرأ شبكةً ولا يكتب ملفّاً؛ يقرأ التقريرَ وحدَه.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

# الأعمدةُ كما في templates/feedback_daily_report.md (حزمة المايسترو) بترتيبها.
EXPECTED_COLUMNS = [
    "#",
    "التذكرة",
    "التاريخ",
    "النوع",
    "الشاشة",
    "المطلوب (ملخص محايد)",
    "مكرر او مرتبط",
    "الاولوية",
    "الاجراء المقترح",
    "الاختصاص",
    "تقدير المدة",
    "اقتراح اخر",
    "قرارك",
]
REQUIRED_SECTIONS = ["## الخلاصة", "## الجدول", "## الحالة في الصندوق"]
MESSAGE_TYPES = {"عطل", "ميزه", "سؤال", "شكوي", "شكر", "اخري"}
PRIORITIES = {"P0", "P1", "P2", "P3"}
SIZES = {"S", "M", "L", "XL"}
TICKET_RE = re.compile(r"SOS-\d{8}-[0-9A-F]{4}")
SUMMARY_MAX = 240  # حدُّ الحقل النصّيّ في ledger.py (FIELD_MAX) — البطاقةُ تُنسخ منه

# ما يُمنع قطعاً في أيّ سطر.
EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
URL_RE = re.compile(r"https?://\S+", re.I)
LONG_DIGITS_RE = re.compile(r"[0-9٠-٩۰-۹]{5,}")
GROUPED_DIGITS_RE = re.compile(
    r"(?<![\d-])(?:[0-9٠-٩۰-۹]{2,4}[ \-]){1,3}[0-9٠-٩۰-۹]{3,4}(?![\d-])"
)
TITLES = (
    "الأستاذة|الاستاذة|الأستاذ|الاستاذ|أستاذة|استاذة|أستاذ|استاذ|المعلمة|المعلم|الطالبة|الطالب|"
    "السيدة|السيد|الأخت|الاخت|الأخ|الاخ|المديرة|المدير|الوكيلة|الوكيل|الدكتورة|الدكتور|"
    "المشرفة|المشرف|المنسقة|المنسق|الموظفة|الموظف"
)
TITLE_SLASH_RE = re.compile(rf"(?:{TITLES})\s*[/\\／]\s*[؀-ۿ]+")
TITLE_WORD_RE = re.compile(rf"(?<![؀-ۿ])(?:و|ل|لل)?(?:{TITLES})\s+([؀-ۿ]+)")
# كلماتٌ تلي اللقبَ في وصفٍ محايدٍ فلا تُعدّ اسماً.
TITLE_FOLLOWERS_OK = {
    "لا", "في", "من", "عن", "على", "الى", "إلى", "مع", "او", "أو", "و", "ثم", "عند", "بعد", "قبل",
    "يطلب", "تطلب", "يشتكي", "تشتكي", "يريد", "تريد", "يقترح", "تقترح", "يسأل", "تسأل",
    "يرى", "ترى", "يجد", "تجد", "يستطيع", "تستطيع", "المسند", "المسندة", "المعني", "المعنية",
    "المذكور", "المذكورة", "الجديد", "الجديدة", "نفسه", "نفسها", "عند", "حين", "إذا", "اذا",
    "الذي", "التي", "دون", "بلا", "ضمن", "داخل", "خارج", "لدى",
}
LATIN_NAME_RE = re.compile(r"\b[A-Z][a-z]{2,}(?:\s+[A-Z][a-z]{2,})+\b")
TECH_LATIN = {
    "Django", "Admin", "Chrome", "Google", "Microsoft", "Edge", "Safari", "Firefox", "Android",
    "Windows", "Excel", "Word", "WhatsApp", "Sentry", "Railway", "Redis", "Celery", "Internet",
    "Explorer", "Samsung", "Huawei", "Apple", "Mac", "Office", "Postgres",
}
QUOTE_RE = re.compile(r"«([^»]{40,})»|\"([^\"]{40,})\"")
# ما يُزال قبل فحص الأرقام: التذكرة والتاريخ والوقت ورقمُ طلب الدمج.
SAFE_NUMERIC_RE = re.compile(
    r"SOS-\d{8}-[0-9A-F]{4}|\b\d{4}-\d{2}-\d{2}(?:[T ]\d{2}:\d{2})?\b|\b\d{2}:\d{2}\b|#\d{1,5}\b"
)
DIACRITICS_RE = re.compile(r"[ً-ٰٟـ]")


def norm(text: str) -> str:
    """توحيدُ الكتابة للمقارنة: بلا تشكيلٍ ولا تطويل، والهمزاتُ ألفاً، والتاءُ المربوطة هاءً."""
    text = DIACRITICS_RE.sub("", text)
    text = re.sub("[أإآٱ]", "ا", text)
    return text.replace("ى", "ي").replace("ة", "ه").strip()


def split_row(line: str) -> list[str]:
    """خلايا صفّ جدول Markdown بلا الحدّين."""
    cells = line.strip().strip("|").split("|")
    return [c.strip() for c in cells]


def find_table(lines: list[str]) -> tuple[list[str] | None, list[tuple[int, list[str]]]]:
    """أوّلُ جدولٍ بعد عنوان «## الجدول»: رأسُه وصفوفُه (برقم السطر)."""
    try:
        start = next(i for i, ln in enumerate(lines) if ln.strip().startswith("## الجدول"))
    except StopIteration:
        return None, []
    header = None
    rows: list[tuple[int, list[str]]] = []
    for i in range(start + 1, len(lines)):
        ln = lines[i].strip()
        if ln.startswith("## "):
            break
        if not ln.startswith("|"):
            if header is not None and rows:
                break
            continue
        cells = split_row(ln)
        if header is None:
            header = cells
        elif all(re.fullmatch(r":?-{3,}:?", c) for c in cells if c):
            continue
        else:
            rows.append((i + 1, cells))
    return header, rows


def scan_leaks(lines: list[str], errors: list[str], warnings: list[str]) -> None:
    """فحصُ التسرّب سطراً سطراً."""
    for no, raw in enumerate(lines, start=1):
        if EMAIL_RE.search(raw):
            errors.append(f"س{no}: بريدٌ إلكترونيّ — يُحذف")
        if URL_RE.search(raw):
            errors.append(f"س{no}: رابطٌ بمضيف — الشاشةُ تُكتب مساراً فقط (/…/)")
        numeric = SAFE_NUMERIC_RE.sub(" ", raw)
        if LONG_DIGITS_RE.search(numeric):
            errors.append(f"س{no}: رقمٌ من خمس خاناتٍ فأكثر (وظيفيّ/شخصيّ/هاتف؟) — يُحذف")
        elif GROUPED_DIGITS_RE.search(numeric):
            errors.append(f"س{no}: أرقامٌ مجزّأةٌ كالهاتف — تُحذف")
        if TITLE_SLASH_RE.search(raw):
            errors.append(f"س{no}: «لقب/ اسم» — لا أسماءَ في المكتوب")
        for m in TITLE_WORD_RE.finditer(raw):
            follower = norm(m.group(1))
            if follower not in {norm(w) for w in TITLE_FOLLOWERS_OK}:
                warnings.append(f"س{no}: «{m.group(0)}» — تأكّد أنّ ما بعد اللقب ليس اسماً")
        for m in LATIN_NAME_RE.finditer(raw):
            if not any(w in TECH_LATIN for w in m.group(0).split()):
                warnings.append(f"س{no}: «{m.group(0)}» يشبه اسماً لاتينيّاً")
        if QUOTE_RE.search(raw):
            warnings.append(f"س{no}: اقتباسٌ طويل — الملخّصُ بكلماتك لا بنصّ الرسالة")


def check(text: str, new_count: int | None) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    lines = text.splitlines()

    for sec in REQUIRED_SECTIONS:
        if not any(ln.strip().startswith(sec) for ln in lines):
            errors.append(f"قسمٌ ناقص: {sec}")

    header, rows = find_table(lines)
    no_news = "لا جديد" in text
    if header is None:
        if not no_news:
            errors.append("لا جدولَ ولا سطرَ «لا جديد»")
    else:
        got = [norm(c) for c in header]
        want = [norm(c) for c in EXPECTED_COLUMNS]
        if got != want:
            errors.append(f"رأسُ الجدول لا يطابق القالب: {len(header)} عموداً بدل {len(want)} أو ترتيبٌ مختلف")
        if not rows and not no_news:
            errors.append("جدولٌ بلا صفوف ولا سطرَ «لا جديد»")

    seen_tickets: set[str] = set()
    has_p0 = False
    for no, cells in rows:
        if len(cells) != len(EXPECTED_COLUMNS):
            errors.append(f"س{no}: {len(cells)} خليّةً بدل {len(EXPECTED_COLUMNS)}")
            continue
        _, ticket, _date, mtype, screen, summary, _dup, prio, _action, _spec, size, _other, _dec = cells
        if not TICKET_RE.fullmatch(ticket):
            errors.append(f"س{no}: التذكرة «{ticket}» ليست بصيغة SOS-YYYYMMDD-XXXX")
        elif ticket in seen_tickets:
            errors.append(f"س{no}: التذكرة مكرّرةٌ في الجدول")
        seen_tickets.add(ticket)
        if norm(mtype) not in MESSAGE_TYPES:
            errors.append(f"س{no}: النوع «{mtype}» خارج (عطل/ميزة/سؤال/شكوى/شكر/أخرى)")
        if prio not in PRIORITIES:
            errors.append(f"س{no}: الأولويّة «{prio}» خارج P0..P3")
        has_p0 = has_p0 or prio == "P0"
        if size not in SIZES:
            errors.append(f"س{no}: تقديرُ المدّة «{size}» خارج S/M/L/XL")
        if screen and not screen.startswith("/") and screen not in {"—", "-", "غير محدد", "غير محدّد"}:
            warnings.append(f"س{no}: الشاشة «{screen}» ليست مساراً يبدأ بـ/")
        if norm(mtype) == norm("شكوى") and "المالك" not in summary:
            errors.append(f"س{no}: شكوى — المطلوبُ «بانتظار سطر المالك» أو «سطر المالك: …» لا ملخّصٌ آليّ")
        if len(summary) > SUMMARY_MAX:
            warnings.append(f"س{no}: الملخّص {len(summary)} حرفاً (> {SUMMARY_MAX}) — لن يدخل بطاقة ledger")

    urgent = next((ln for ln in lines if "العاجل" in ln), "")
    if has_p0 and ("لا شيء" in urgent or not urgent):
        errors.append("في الجدول P0 وسطرُ «العاجل» يقول «لا شيء» أو غائب — أبلغ المايسترو فوراً")

    if new_count is not None and header is not None and len(rows) != new_count:
        warnings.append(f"صفوفُ الجدول {len(rows)} والجديدُ المعلَن {new_count} — الجدولُ للجديد وحدَه")

    scan_leaks(lines, errors, warnings)
    return errors, warnings


def main() -> int:
    parser = argparse.ArgumentParser(description="مدقّق تقرير أمين البلاغات اليوميّ")
    parser.add_argument("report", help="ملفُّ التقرير (Markdown)")
    parser.add_argument("--new-count", type=int, default=None, help="عددُ الرسائل الجديدة المعلَن")
    args = parser.parse_args()
    path = Path(args.report)
    if not path.is_file():
        print(f"لا ملفّ: {path}", file=sys.stderr)
        return 2
    errors, warnings = check(path.read_text(encoding="utf-8"), args.new_count)
    for w in warnings:
        print("تنبيه: " + w)
    for e in errors:
        print("خطأ:   " + e)
    print(f"\n{'راسب' if errors else 'ناجح'} — {len(errors)} خطأ، {len(warnings)} تنبيه")
    return 1 if errors else 0


if __name__ == "__main__":
    # طرفيّةُ ويندوز ترمّز cp1256 افتراضاً فتفسد العربيّة؛ نفرض UTF-8 للمخرجين.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    sys.exit(main())

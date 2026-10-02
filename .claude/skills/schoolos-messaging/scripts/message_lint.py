#!/usr/bin/env python3
"""فاحصٌ حتميٌّ لنصّ رسالةٍ بين الجلسات قبل إرسالها، بالمكتبة القياسيّة وحدها.

    python message_lint.py --kind request --file msg.txt
    cat msg.txt | python message_lint.py --kind auto
    python message_lint.py --kind relay --file msg.txt --strict

الأنواع: request (يطلب عملاً)، relay (ينقل قراراً من المالك)، rule (يغيّر قاعدةً، يبدأ «الفلو vX.Y»)،
reply (ردّ)، info (للعلم)، auto (يُستنتج من النصّ).

المخرج: JSON على stdout، وسطرٌ عربيٌّ لكلّ مخالفةٍ على stderr.
رمزُ الخروج: 0 لا أخطاء (قد توجد تحذيرات)، 1 أخطاء (أو تحذيرات مع --strict)، 2 خطأُ استعمال.

حدُّ الطول (1500 حرف أو 20 سطراً غيرَ فارغ): أطولُ قالبٍ في references/03-templates.md
عشرةُ أسطرٍ نحو 700 حرف، فالحدُّ ضعفُه تقريباً؛ ما فوقه تقريرٌ مكانُه ملفٌّ يُشار إليه.
وحدُّ السطر الأوّل (200 حرف): المستلِمُ يرى السطرَ الأوّل وحدَه معاينةً (وصفُ أداة SendMessage).
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

MAX_CHARS = 1500
MAX_LINES = 20
MAX_FIRST_LINE = 200
ARABIC_ERROR_BELOW = 0.70
ARABIC_WARN_BELOW = 0.90
MIN_LETTERS_FOR_RATIO = 20

ARABIC_LETTER = re.compile(r"[\u0621-\u063A\u0641-\u064A\u0671-\u06D3\u06FA-\u06FF]")
LATIN_LETTER = re.compile(r"[A-Za-z]")
# التشكيلُ والتطويل: يُزالان قبل مطابقة الكلمات
TASHKEEL = re.compile(r"[\u064B-\u065F\u0670\u0640]")

# ما يُحذف قبل حساب نسبة العربيّة: شيفرةٌ ومساراتٌ وروابطُ ومعرّفات
FENCED = re.compile(r"```.*?```", re.S)
INLINE_CODE = re.compile(r"`[^`\n]*`")
URL = re.compile(r"https?://\S+")
PATHLIKE = re.compile(r"\S*[/\\]\S*")
FILE_WITH_EXT = re.compile(r"\b[\w.-]+\.[A-Za-z]{1,5}\b")
IDENT_WITH_DIGIT = re.compile(r"\b[\w-]*\d[\w-]*\b")
# مصطلحاتٌ تقنيّةٌ شائعةٌ تُكتب بالإنجليزيّة داخل الجملة العربيّة
ALLOWED_TERMS = {
    "pr", "ci", "css", "js", "html", "pdf", "excel", "json", "api", "url", "bluf", "wip", "sha",
    "pytest", "ruff", "mypy", "git", "gh", "main", "commit", "push", "merge", "diff", "rebase",
    "sendmessage", "listagents", "preview", "pin", "release", "status", "docker", "chrome",
    "sentry", "railway", "queued", "delivered", "undelivered", "askuserquestion", "claude", "code",
    "e2e", "ruff", "celery", "django", "htmx", "rtl", "ok",
}

GREETINGS = (
    "السلام", "سلام", "مرحبا", "اهلا", "أهلا", "هلا", "صباح الخير", "مساء الخير", "تحية", "تحيه",
    "عزيزي", "الزميل", "زميلي", "يا زميل", "hi", "hello", "hey", "dear", "greetings",
)
PREAMBLES = (
    "أود", "اود", "أريد أن", "اريد ان", "بخصوص", "بالإشارة", "بالاشارة", "إشارة إلى", "اشارة الى",
    "كما تعلم", "كما ناقشنا", "لدي سؤال", "عندي سؤال", "آسف على", "اسف على", "معذرة", "أرجو المعذرة",
    "قبل أن أبدأ", "قبل ان ابدا", "أتمنى", "اتمنى", "fyi", "just wanted", "i wanted", "as discussed",
)

# أنماطٌ حسّاسة
LONG_NUMBER = re.compile(r"(?<![\w\-#])\d{8,}(?![\w\-])")
PHONE_QA = re.compile(r"(?:\+|00)974[\s-]?\d{4}[\s-]?\d{4}")
EMAIL = re.compile(r"\b[\w.+-]+@[\w-]+(?:\.[\w-]+)+\b")
SECRET_PATTERNS = [
    re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}"),
    re.compile(r"\bgithub_pat_[A-Za-z0-9_]{20,}"),
    re.compile(r"\bsk-(?:ant-)?[A-Za-z0-9_-]{20,}"),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    re.compile(r"\bxox[abpr]-[A-Za-z0-9-]{10,}"),
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    re.compile(r"(?i)\b(?:password|passwd|secret|token|api[_-]?key)\s*[:=]\s*\S+"),
]
HIGH_ENTROPY = re.compile(r"(?<![\w/\\.-])[A-Za-z0-9_\-]{32,}(?![\w/\\.-])")
PURE_HEX = re.compile(r"^[0-9a-fA-F]+$")
PROD_HOST = re.compile(r"(?i)\b[\w.-]*(?:railway\.app|railway\.internal|rlwy\.net)\b")
CONN_STRING = re.compile(r"(?i)\b(?:postgres(?:ql)?|redis|rediss|mysql|amqp|mongodb)://\S+")
URL_HOST = re.compile(r"https?://([^/\s:]+)")
SAFE_HOSTS = {"localhost", "127.0.0.1", "github.com", "claude.ai", "docs.claude.com"}
SESSION_PORT = re.compile(r"(?<![\d.:/#-])8[0-2]\d\d(?!\d)")
AT_ATTACH = re.compile(r"(?<!\S)@(?:[A-Za-z]:)?[\w./\\-]+")
TEMP_PATH = re.compile(r"(?i)(?:AppData[\\/]Local[\\/]Temp|/tmp/|scratchpad)")
ON_BEHALF = re.compile(r"نيابة\s*عن\s*المالك|بالنيابة\s*عن\s*المالك|أعتمده?\s*عنك|اعتمده?\s*عنك")
PROD_COMMAND = re.compile(r"(?i)railway\s+(?:up|run|ssh|redeploy|variables)|push\s+(?:-f\b|--force)|--force-with-lease|gh\s+pr\s+merge|drop\s+table")
BYPASS = re.compile(r"--no-verify|تجاوز\s*(?:البوّابة|البوابة|الحارس|الفحص)|عطّل\s*(?:الحارس|البوّابة)|عطل\s*(?:الحارس|البوابة)")

# علاماتُ الأنواع
RELAY_HINT = re.compile(r"نقل\s*قرار|النص\s*الحرفي|قال\s*المالك|قرار\s*المالك|أمر\s*المالك|امر\s*المالك|اعتمد\s*المالك")
REQUEST_HINT = re.compile(r"المطلوب|أرجو|ارجو|يرجى|نرجو|اطلب|نفذ|أرسل لي|ارسل لي|[?؟]")
INFO_HINT = re.compile(r"لا\s*رد\s*مطلوب|للعلم|المطلوب\s*:\s*لا\s*شيء")
QUOTED = re.compile(r"«([^»]{3,})»|\"([^\"]{3,})\"|“([^”]{3,})”")
TIME = re.compile(r"(?<!\d)(?:[01]?\d|2[0-3]):[0-5]\d(?!\d)")
FLOW_PREFIX = re.compile(r"^الفلو v\d+\.\d+")
DECISION_REF = re.compile(r"\bD-\d+م?")


def normalize(text: str) -> str:
    """يزيل التشكيلَ والتطويلَ ليُطابَق النصُّ بلا أثرٍ للضبط."""
    return TASHKEEL.sub("", text)


def strip_for_ratio(text: str) -> str:
    """يحذف الشيفرةَ والمساراتِ والروابطَ والمعرّفاتِ والمصطلحاتِ المسموحة قبل عدّ الحروف."""
    for pattern in (FENCED, INLINE_CODE, URL, PATHLIKE, FILE_WITH_EXT, IDENT_WITH_DIGIT):
        text = pattern.sub(" ", text)
    words = [w for w in re.split(r"\s+", text) if w]
    kept = [w for w in words if re.sub(r"[^A-Za-z]", "", w).lower() not in ALLOWED_TERMS]
    return " ".join(kept)


def arabic_ratio(text: str) -> tuple[float | None, int]:
    """نسبةُ الحروف العربيّة إلى مجموع العربيّة واللاتينيّة، بعد الحذف؛ None إن قلّت الحروف."""
    body = strip_for_ratio(normalize(text))
    ar = len(ARABIC_LETTER.findall(body))
    la = len(LATIN_LETTER.findall(body))
    total = ar + la
    if total < MIN_LETTERS_FOR_RATIO:
        return None, total
    return ar / total, total


def starts_with_word(line: str, phrase: str) -> bool:
    """هل يبدأ السطرُ بالعبارة كلمةً تامّة (يليها فراغٌ أو ترقيمٌ أو نهاية)؟"""
    phrase = normalize(phrase).lower()
    return re.match(re.escape(phrase) + r"(?:$|[\s,،:!.؟?؛-])", line) is not None


def line_of(text: str, index: int) -> int:
    """رقمُ السطر (من 1) لموضعٍ في النصّ."""
    return text.count("\n", 0, index) + 1


def detect_kind(text: str) -> str:
    """يستنتج نوعَ الرسالة من علاماتها حين لا يُعطى النوع."""
    norm = normalize(text)
    first = norm.strip().splitlines()[0] if norm.strip() else ""
    if FLOW_PREFIX.match(first):
        return "rule"
    if RELAY_HINT.search(norm):
        return "relay"
    if INFO_HINT.search(norm):
        return "info"
    if REQUEST_HINT.search(norm):
        return "request"
    return "info"


def lint(text: str, kind: str = "auto") -> dict:
    """يفحص النصّ ويعيد قاموساً: النوع، والإحصاءات، وقائمةَ المخالفات."""
    findings: list[dict] = []

    def add(code: str, severity: str, message: str, line: int | None = None) -> None:
        findings.append({"code": code, "severity": severity, "line": line, "message": message})

    detected = kind == "auto"
    if detected:
        kind = detect_kind(text)

    stripped = text.strip()
    if not stripped:
        add("EMPTY", "error", "الرسالةُ فارغة")
        return {"ok": False, "kind": kind, "kind_detected": detected, "stats": {}, "findings": findings}

    lines = text.splitlines()
    first_idx = next(i for i, ln in enumerate(lines) if ln.strip())
    first = lines[first_idx].strip()
    first_norm = normalize(first).lower()
    first_line_no = first_idx + 1

    # 1) السطرُ الأوّل خلاصةٌ لا تحيّة ولا تمهيد (بحدّ كلمةٍ: «سلامةُ الهجرة» ليست تحيّة، و«أودعتُ» ليست «أودّ»)
    if any(starts_with_word(first_norm, g) for g in GREETINGS):
        add("FIRST_LINE_GREETING", "error", "السطرُ الأوّل تحيّة؛ اجعله الخلاصةَ والمطلوب (المستلِمُ يرى هذا السطرَ وحدَه)", first_line_no)
    elif any(starts_with_word(first_norm, p) for p in PREAMBLES):
        add("FIRST_LINE_PREAMBLE", "error", "السطرُ الأوّل تمهيد؛ ابدأ بالخلاصة (BLUF)", first_line_no)
    if re.fullmatch(r"@\S+[\s,،:]*", first) or re.fullmatch(r"«[^»]+»[\s,،:]*", first):
        add("FIRST_LINE_BARE_MENTION", "error", "السطرُ الأوّل اسمٌ أو إشارةٌ وحدَها بلا مضمون", first_line_no)
    if not ARABIC_LETTER.search(first):
        add("FIRST_LINE_NOT_ARABIC", "error", "السطرُ الأوّل بلا عربيّة؛ الرسالةُ بالعربيّة وحدها", first_line_no)
    if len(first) > MAX_FIRST_LINE:
        add("FIRST_LINE_TOO_LONG", "warning", f"السطرُ الأوّل {len(first)} حرفاً (> {MAX_FIRST_LINE})؛ المعاينةُ تقصّه — اختصر الخلاصة", first_line_no)

    # 2) نسبةُ العربيّة
    ratio, letters = arabic_ratio(text)
    if ratio is not None:
        pct = round(ratio * 100)
        if ratio < ARABIC_ERROR_BELOW:
            add("ARABIC_RATIO", "error", f"العربيّةُ {pct}% من الحروف خارج الشيفرة؛ اكتب النصَّ بالعربيّة وضع الأوامرَ والمساراتِ بين ` `")
        elif ratio < ARABIC_WARN_BELOW:
            add("ARABIC_RATIO", "warning", f"العربيّةُ {pct}% من الحروف خارج الشيفرة؛ ضع المصطلحاتِ والأوامرَ بين ` `")

    # 3) الطول
    nonempty = [ln for ln in lines if ln.strip()]
    if len(stripped) > MAX_CHARS or len(nonempty) > MAX_LINES:
        add("TOO_LONG", "warning", f"الرسالةُ {len(stripped)} حرفاً و{len(nonempty)} سطراً؛ انقل التفصيلَ إلى ملفٍّ مقروءٍ عند المستلِم وأشِر إليه")

    # 4) الحسّاس
    for m in LONG_NUMBER.finditer(text):
        add("LONG_NUMBER", "error", "رقمٌ طويل (8 خاناتٍ فأكثر) قد يكون وطنيّاً أو وظيفيّاً أو هاتفاً؛ احذفه", line_of(text, m.start()))
    for m in PHONE_QA.finditer(text):
        add("PHONE", "error", "رقمُ هاتف؛ احذفه", line_of(text, m.start()))
    for m in EMAIL.finditer(text):
        add("EMAIL", "error", "عنوانُ بريد؛ احذفه", line_of(text, m.start()))
    secret_spans: list[tuple[int, int]] = []
    for pattern in SECRET_PATTERNS:
        for m in pattern.finditer(text):
            secret_spans.append(m.span())
            add("SECRET", "error", "ما يشبه مفتاحاً أو رمزَ وصولٍ أو كلمةَ مرور؛ لا أسرارَ في الرسائل", line_of(text, m.start()))
    for m in HIGH_ENTROPY.finditer(text):
        if any(s <= m.start() < e for s, e in secret_spans):
            continue
        token = m.group(0)
        if PURE_HEX.match(token):
            add("FULL_HASH", "warning", "سلسلةٌ ستّ عشريّةٌ طويلة (رأسٌ كامل؟)؛ الرأسُ المختصر يكفي، وتأكّد أنّها ليست سرّاً", line_of(text, m.start()))
            continue
        # اسمٌ مركّبٌ بفواصل (اسمُ ملفّ ذاكرة، فرع) ليس رمزاً: المعتبرُ مقطعٌ متّصلٌ طويلٌ يخلط الحروفَ والأرقام
        if any(len(seg) >= 20 and re.search(r"[A-Za-z]", seg) and re.search(r"\d", seg)
               for seg in re.split(r"[_-]", token)):
            add("HIGH_ENTROPY", "error", "سلسلةٌ طويلةٌ عشوائيّة قد تكون رمزاً سرّيّاً؛ احذفها", line_of(text, m.start()))
    for m in PROD_HOST.finditer(text):
        add("PROD_HOST", "error", "مضيفُ إنتاجٍ أو شبكةٍ داخليّة؛ لا يُكتب في رسالة", line_of(text, m.start()))
    for m in CONN_STRING.finditer(text):
        add("CONN_STRING", "error", "سلسلةُ اتّصالٍ بقاعدةٍ أو وسيط؛ احذفها", line_of(text, m.start()))
    for m in URL_HOST.finditer(text):
        host = m.group(1).lower()
        if host not in SAFE_HOSTS and not PROD_HOST.search(host):
            add("URL_HOST", "warning", f"رابطٌ إلى «{host}»؛ تأكّد أنّه ليس مضيفَ إنتاج", line_of(text, m.start()))
    for m in SESSION_PORT.finditer(text):
        if m.group(0) != "8500":
            add("SESSION_PORT", "warning", f"الرقم {m.group(0)} يشبه منفذَ جلسة؛ خاطب الجلسةَ باسمها من القائمة الحيّة", line_of(text, m.start()))

    # 5) الملفّات والإرفاق
    for m in AT_ATTACH.finditer(text):
        add("AT_ATTACH", "warning", "«@مسار» لا يُرفق شيئاً عند المستلِم؛ اكتب المسارَ المطلقَ نصّاً أو انسخ المحتوى", line_of(text, m.start()))
    for m in TEMP_PATH.finditer(text):
        add("TEMP_PATH", "warning", "مسارٌ في المؤقّت قد يُمسح؛ ضع الملفَّ في ~/<اسم>_work/", line_of(text, m.start()))

    # 6) ما لا يُطلب برسالة
    norm_text = normalize(text)
    for m in ON_BEHALF.finditer(norm_text):
        add("ON_BEHALF", "warning", "تأكّد: لا اعتمادَ نيابةً عن المالك برسالة", line_of(norm_text, m.start()))
    for m in PROD_COMMAND.finditer(text):
        add("PROD_COMMAND", "warning", "أمرُ إنتاجٍ أو دمجٍ أو دفعٍ قسريّ؛ لا يُطلب من جلسةٍ برسالة (بأمر المالك حيث يُنفَّذ)", line_of(text, m.start()))
    for m in BYPASS.finditer(norm_text):
        add("BYPASS", "warning", "طلبُ تجاوز بوّابةٍ أو حارس؛ لا يُرسَل", line_of(norm_text, m.start()))

    # 7) حقولُ النوع
    if kind == "request":
        if "المطلوب" not in norm_text:
            add("MISSING_REQUIRED", "error", "رسالةُ طلبٍ بلا «المطلوب»؛ اذكر ما يفعله المستلِم بالضبط")
        if "مهلة" not in norm_text:
            add("MISSING_DEADLINE", "error", "رسالةُ طلبٍ بلا «المهلة»؛ اذكر متى (وقتٌ أو نافذة)")
        if not re.search(r"الرد|للرد|رد\s*ب|ردك", norm_text):
            add("MISSING_REPLY_HOW", "warning", "لم تذكر كيف يردّ المستلِم")
    elif kind == "relay":
        if not QUOTED.search(text):
            add("RELAY_NO_QUOTE", "error", "نقلُ قرارٍ بلا نصّ المالك الحرفيّ بين «»")
        if not TIME.search(text):
            add("RELAY_NO_TIME", "error", "نقلُ قرارٍ بلا وقتٍ (HH:MM بالدوحة من الجهاز)")
        if not re.search(r"محادثة|AskUserQuestion", norm_text):
            add("RELAY_NO_PLACE", "warning", "لم تذكر المحادثةَ التي قيل فيها القرار")
        if "يشمل" not in norm_text:
            add("RELAY_NO_SCOPE", "warning", "لم تذكر ما يشمله القرار")
        if "لا يشمل" not in norm_text:
            add("RELAY_NO_EXCLUSION", "warning", "لم تذكر ما لا يشمله القرار؛ بغيابه يُفهم أوسعَ ممّا قُصد")
    elif kind == "rule":
        if not FLOW_PREFIX.match(normalize(first)):
            add("RULE_NO_FLOW_VERSION", "error", "رسالةُ تغيير قاعدةٍ تبدأ بـ«الفلو vX.Y»", first_line_no)
        if not DECISION_REF.search(text):
            add("RULE_NO_DECISION", "warning", "لم تذكر رقمَ القرار المسجَّل (D-…م)")

    ok = not any(f["severity"] == "error" for f in findings)
    stats = {"chars": len(stripped), "lines": len(nonempty),
             "arabic_ratio": None if ratio is None else round(ratio, 3), "letters_counted": letters}
    return {"ok": ok, "kind": kind, "kind_detected": detected, "stats": stats, "findings": findings}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="فحصُ رسالةٍ بين الجلسات قبل إرسالها")
    parser.add_argument("--kind", default="auto", choices=["auto", "request", "relay", "rule", "reply", "info"])
    parser.add_argument("--file", help="ملفُّ نصّ الرسالة (وإلّا stdin)")
    parser.add_argument("--strict", action="store_true", help="التحذيراتُ تُسقط الفحصَ أيضاً")
    args = parser.parse_args(argv)

    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    try:
        text = Path(args.file).read_text(encoding="utf-8") if args.file else sys.stdin.buffer.read().decode("utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        print(f"تعذّرت قراءةُ الرسالة: {exc}", file=sys.stderr)
        return 2

    result = lint(text, args.kind)
    label = {"error": "خطأ", "warning": "تحذير"}
    for f in result["findings"]:
        where = f" (س{f['line']})" if f["line"] else ""
        print(f"[{label[f['severity']]}] {f['code']}{where}: {f['message']}", file=sys.stderr)
    errors = sum(f["severity"] == "error" for f in result["findings"])
    warnings = len(result["findings"]) - errors
    print(f"النوع: {result['kind']} — أخطاء: {errors} — تحذيرات: {warnings}", file=sys.stderr)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if errors or (args.strict and warnings):
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

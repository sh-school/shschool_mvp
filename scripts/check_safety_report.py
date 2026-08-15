"""[SEC-GATE] حَكَمُ تقرير Safety — يفشل مغلقاً.

    python scripts/check_safety_report.py safety-report.json

كان هذا المنطق مضمَّناً في `security-scan.yml`، وكان **يفشل مفتوحاً** في
حالتين: تقريرٌ غائب يطبع سطراً ويخرج بنجاح، وتقريرٌ لا يُحلَّل يطبع تحذيراً
ويخرج بنجاح. و`safety check ... || true` قبله يبتلع فشل الأداة نفسها — فسقوط
الشبكة أو خطأ في المعامِلات كان يُنتج «لا ثغرات» بدل «لم أفحص».

والفرق حاسم لأن هذه الوظيفة صارت تحكم بوابة الدمج: «لم أفحص» يجب أن تُغلق
البوابة كما تُغلقها «وجدتُ ثغرة»، لا أن تمرّ بصمت.

وأُخرج إلى ملفّ ليُختبر: منطقٌ داخل YAML لا يُشغّله أحدٌ إلا CI، فلا يُكتشف
عطبه إلا حين يُحتاج إليه.
"""

import json
import pathlib
import sys

BLOCKING_SEVERITIES = {"HIGH", "CRITICAL"}


def evaluate(path):
    """يُعيد `(exit_code, message)` — و`0` تعني «فُحص ولم يُوجد شيءٌ حاجب»."""
    report = pathlib.Path(path)

    if not report.exists():
        return 1, f"FAIL: تقرير Safety غير موجود ({path}) — لم يقع فحصٌ يُعتمد عليه"

    try:
        raw = report.read_text(encoding="utf-8")
    except OSError as exc:
        return 1, f"FAIL: تعذّرت قراءة التقرير — {type(exc).__name__}"

    if not raw.strip():
        return 1, "FAIL: التقرير فارغ — لم يقع فحصٌ يُعتمد عليه"

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        return 1, f"FAIL: التقرير غير قابل للتحليل — {exc.msg}"

    if not isinstance(data, dict):
        return 1, f"FAIL: بنية التقرير غير متوقَّعة — {type(data).__name__}"

    vulnerabilities = data.get("vulnerabilities")

    if vulnerabilities is None:
        return 1, "FAIL: التقرير بلا حقل `vulnerabilities` — بنيةٌ لا نعرفها"

    if not isinstance(vulnerabilities, list):
        return 1, "FAIL: `vulnerabilities` ليست قائمة — بنيةٌ لا نعرفها"

    blocking = [
        item
        for item in vulnerabilities
        if isinstance(item, dict) and str(item.get("severity", "")).upper() in BLOCKING_SEVERITIES
    ]

    if blocking:
        lines = [f"FAIL: {len(blocking)} ثغرة HIGH/CRITICAL:"]
        lines += [
            f"  - {item.get('package_name')}: {item.get('vulnerability_id')} "
            f"({item.get('severity')})"
            for item in blocking
        ]
        return 1, "\n".join(lines)

    return 0, f"PASS: لا ثغرات HIGH/CRITICAL ({len(vulnerabilities)} نتيجة إجمالاً)"


def main(argv):
    if len(argv) != 2:
        print("usage: check_safety_report.py <report.json>", file=sys.stderr)
        return 2

    code, message = evaluate(argv[1])
    print(message)

    return code


if __name__ == "__main__":  # pragma: no cover — نقطة الدخول
    sys.exit(main(sys.argv))

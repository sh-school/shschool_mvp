#!/usr/bin/env python3
"""اختباراتُ message_lint.py بحالاتٍ سليمةٍ ومعيبة (كلُّ البيانات مختلَقة).

    python -m unittest test_message_lint.py -v      (من مجلّد scripts)
"""

from __future__ import annotations

import json
import subprocess
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import message_lint as ml  # noqa: E402

GOOD_READY = """جاهزٌ للمعاينة: فلترُ الأجنحة في سجلّ المخالفات يحصر القائمة — المطلوب: إدراجٌ في نافذة 20:30
1) ما تغيّر: قائمةُ «الجناح» تحصر الطلبةَ المعروضين في السجلّ.
2) أين يُرى: `/behavior/log/` بدور مشرف الجناح.
3) الخطورة: متوسّطة (قالبٌ مرئيّ)؛ لا هجرة.
4) الفحوص: `pytest tests/test_wing_filter.py` (9 ناجحة)، `ruff` نظيف.
5) الرجوع: عكسُ الإيداع `abc1234` وحده.
الشجرة: `calm-example-1a2b3c` — الرأس: `abc1234` — مودَعٌ غيرُ مدفوع
المهلة: نافذةُ 20:30 — الردّ: اعتمادٌ أو ملاحظات في محادثتي
"""

GOOD_RELAY = """نقلُ قرارٍ من المالك: اعتمادُ الجزأين 1 و2 من Z-17 — المطلوب: الدفعُ وإضافةُ سطر الاعتماد
النصُّ الحرفيّ: «اعتمد الاثنين بعد ما شفتهم»
الوقت: 2026-09-28 20:41 الدوحة (من الجهاز)
المكان: محادثة «0101 · المايسترو»
يشمل: الجزأين 1 و2.
لا يشمل: الجزء 3 (لم يُعاين) ولا أيَّ هجرة.
المرجع: لم يُسجَّل بعد
المهلة: الليلة — الردّ: إن اختلف فهمُك فاسأل المالكَ في محادثتك بنعم أو لا
"""

GOOD_RULE = """الفلو v9.1: رسائلُ العلم تُجمع في رسالةٍ واحدةٍ مساءً — المطلوب: العملُ بها من الغد
القرار: D-901م (2026-09-28 20:50) — سطرُ السجلّ: flow_changelog.md v9.1
ما تغيّر: قبلُ رسالةٌ لكلّ خطوة، وبعدُ ملخّصٌ واحد.
الردّ: لا ردَّ مطلوب؛ السؤالُ إلى «0103 · الحوكمة»
"""

GOOD_INFO = """اكتشاف: زرُّ تصدير كشف الشعبة يصدّر الشعبةَ المختارة سابقاً — المطلوب: بطاقة، لن أصلحه
المشكلة: التصديرُ يقرأ اختياراً قديماً من الجلسة بعد تغيير الشعبة.
الأثر: مشرفو الأجنحة عند التبديل بين شعبتين.
الملفّاتُ المظنونة: `wings/views.py`
معيارُ القبول: الملفُّ المصدَّر يطابق الشعبةَ المعروضة.
لا ردَّ مطلوب.
"""


def codes(result: dict, severity: str | None = None) -> set[str]:
    return {f["code"] for f in result["findings"] if severity is None or f["severity"] == severity}


class GoodMessages(unittest.TestCase):
    def test_ready_for_preview_is_clean(self):
        r = ml.lint(GOOD_READY, "request")
        self.assertTrue(r["ok"], r["findings"])
        self.assertEqual(codes(r, "error"), set())

    def test_relay_is_clean(self):
        r = ml.lint(GOOD_RELAY, "relay")
        self.assertTrue(r["ok"], r["findings"])
        self.assertFalse(codes(r) & {"RELAY_NO_SCOPE", "RELAY_NO_EXCLUSION", "RELAY_NO_PLACE"})

    def test_rule_is_clean(self):
        r = ml.lint(GOOD_RULE, "rule")
        self.assertTrue(r["ok"], r["findings"])

    def test_auto_detection(self):
        self.assertEqual(ml.lint(GOOD_RELAY)["kind"], "relay")
        self.assertEqual(ml.lint(GOOD_RULE)["kind"], "rule")
        self.assertEqual(ml.lint(GOOD_INFO)["kind"], "info")
        self.assertEqual(ml.lint(GOOD_READY)["kind"], "request")

    def test_word_boundaries_avoid_false_greeting(self):
        # «سلامةُ» ليست «سلام»، و«أودعتُ» ليست «أودّ»
        for first in ("سلامةُ الهجرة: لا حذفَ أعمدة — المطلوب: لا شيء", "أودعتُ فلترَ الأجنحة محلّيّاً — المطلوب: لا شيء"):
            r = ml.lint(first + "\nلا ردَّ مطلوب.", "info")
            self.assertFalse(codes(r) & {"FIRST_LINE_GREETING", "FIRST_LINE_PREAMBLE"}, first)

    def test_ids_and_memory_names_are_not_secrets(self):
        text = ("للخارطة: Z-17 — #9912 اندمج — المطلوب: تحديثُ البند\n"
                "المرجع: W-20260928-001 وSOS-20260927-3310 والملفّ project_session_lanes_proposal_2026_09_25\n"
                "لا ردَّ مطلوب.")
        r = ml.lint(text, "info")
        self.assertEqual(codes(r, "error"), set(), r["findings"])

    def test_8500_is_allowed(self):
        r = ml.lint("سطرُ الاعتماد: «اعتُمد من المالك على 8500 — 2026-09-28» موجود — المطلوب: لا شيء\nلا ردَّ مطلوب.", "info")
        self.assertNotIn("SESSION_PORT", codes(r))


class BadMessages(unittest.TestCase):
    def test_greeting_first_line(self):
        r = ml.lint("السلام عليكم، أتمنّى أن تكون بخير\nالمطلوب: مراجعة. المهلة: اليوم. الردّ هنا.", "request")
        self.assertIn("FIRST_LINE_GREETING", codes(r, "error"))
        self.assertFalse(r["ok"])

    def test_preamble_first_line(self):
        r = ml.lint("بخصوص الموضوع الذي تكلّمنا عنه\nالمطلوب: مراجعة. المهلة: اليوم. الردّ هنا.", "request")
        self.assertIn("FIRST_LINE_PREAMBLE", codes(r, "error"))

    def test_bare_mention(self):
        r = ml.lint("@0601\nالمطلوب: دمج. المهلة: الليلة. الردّ هنا.", "request")
        self.assertIn("FIRST_LINE_BARE_MENTION", codes(r, "error"))

    def test_english_message(self):
        r = ml.lint("Ready for preview: the wing filter now narrows the list and the tests pass locally, please pin it on the preview server today.", "request")
        self.assertIn("FIRST_LINE_NOT_ARABIC", codes(r, "error"))
        self.assertIn("ARABIC_RATIO", codes(r, "error"))

    def test_request_without_required_and_deadline(self):
        r = ml.lint("شوف موضوع التصدير وخلّصه لو سمحت", "request")
        self.assertTrue({"MISSING_REQUIRED", "MISSING_DEADLINE"} <= codes(r, "error"))

    def test_relay_without_quote_or_time(self):
        r = ml.lint("نقلُ قرارٍ من المالك: المالكُ اعتمد كلَّ شيء — المطلوب: ادفعوا الآن", "relay")
        self.assertTrue({"RELAY_NO_QUOTE", "RELAY_NO_TIME"} <= codes(r, "error"))
        self.assertIn("RELAY_NO_EXCLUSION", codes(r, "warning"))

    def test_rule_without_flow_version(self):
        r = ml.lint("قاعدةٌ جديدة: رسائلُ العلم تُجمع مساءً — المطلوب: العملُ بها", "rule")
        self.assertIn("RULE_NO_FLOW_VERSION", codes(r, "error"))
        self.assertIn("RULE_NO_DECISION", codes(r, "warning"))

    def test_sensitive_patterns(self):
        # القيمُ تُركَّب وقتَ التشغيل كي لا تطابق ماسحاتِ الأسرار والهويّات في المستودع العامّ
        fake_id = "2" + "0" * 10
        fake_phone = "+974 " + "5" * 4 + " " + "0" * 4
        fake_mail = "someone" + "@" + "example.org"
        fake_key = "gh" + "p_" + "A" * 36
        fake_host = "web-prod.up." + "railway.app"
        fake_conn = "postgres" + "://u:p@db:5432/x"
        text = ("اكتشاف: خطأٌ في ملفّ معلّم — المطلوب: بطاقة\n"
                f"الرقمُ الشخصيّ {fake_id} والهاتف {fake_phone} والبريد {fake_mail}\n"
                "tok" + f"en=abcd1234efgh والمضيف {fake_host} والاتّصال {fake_conn}\n"
                f"ومفتاح {fake_key}\n")
        r = ml.lint(text, "info")
        self.assertTrue({"LONG_NUMBER", "PHONE", "EMAIL", "SECRET", "PROD_HOST", "CONN_STRING"} <= codes(r, "error"), codes(r))

    def test_high_entropy_token(self):
        token = "Zx9Qw" + "ErT5yUi8oP" + "aS3dF7gHj2kLm4nBv"
        r = ml.lint(f"اكتشاف: رمزٌ في السجلّ — المطلوب: بطاقة\nالرمز: {token}\nلا ردَّ مطلوب.", "info")
        self.assertIn("HIGH_ENTROPY", codes(r, "error"))

    def test_session_port_and_attach_and_temp(self):
        text = ("حال: أرسلتُ إلى 8098 — المطلوب: لا شيء\n"
                "التفصيل في @~/AppData/Local/Temp/x/report.md\nلا ردَّ مطلوب.")
        r = ml.lint(text, "info")
        self.assertTrue({"SESSION_PORT", "AT_ATTACH", "TEMP_PATH"} <= codes(r, "warning"), codes(r))
        self.assertTrue(r["ok"])  # تحذيراتٌ لا أخطاء

    def test_prod_command_and_bypass(self):
        text = "تصعيد: الطابور عالق — المطلوب: نفّذ `railway up` وتجاوز البوّابة بـ`--no-verify`\nالمهلة: الآن — الردّ هنا"
        r = ml.lint(text, "request")
        self.assertTrue({"PROD_COMMAND", "BYPASS"} <= codes(r, "warning"), codes(r))

    def test_too_long(self):
        body = "\n".join(f"سطرُ تفصيلٍ رقم {i} يشرح جزءاً من التقرير الطويل." for i in range(30))
        r = ml.lint("حال: تقريرٌ طويل — المطلوب: لا شيء\n" + body + "\nلا ردَّ مطلوب.", "info")
        self.assertIn("TOO_LONG", codes(r, "warning"))

    def test_empty(self):
        r = ml.lint("   \n  ", "auto")
        self.assertIn("EMPTY", codes(r, "error"))


class CommandLine(unittest.TestCase):
    def run_cli(self, text: str, *args: str) -> subprocess.CompletedProcess:
        return subprocess.run([sys.executable, str(HERE / "message_lint.py"), *args],
                              input=text.encode("utf-8"), capture_output=True)

    def test_exit_zero_and_json_on_good(self):
        p = self.run_cli(GOOD_READY, "--kind", "request")
        self.assertEqual(p.returncode, 0, p.stderr.decode("utf-8"))
        data = json.loads(p.stdout.decode("utf-8"))
        self.assertTrue(data["ok"])

    def test_exit_one_and_arabic_lines_on_bad(self):
        p = self.run_cli("السلام عليكم\nشوف الموضوع", "--kind", "request")
        self.assertEqual(p.returncode, 1)
        err = p.stderr.decode("utf-8")
        self.assertIn("[خطأ] FIRST_LINE_GREETING", err)
        self.assertIn("النوع: request", err)

    def test_strict_fails_on_warnings(self):
        text = "حال: أرسلتُ إلى 8098 — المطلوب: لا شيء\nلا ردَّ مطلوب."
        self.assertEqual(self.run_cli(text, "--kind", "info").returncode, 0)
        self.assertEqual(self.run_cli(text, "--kind", "info", "--strict").returncode, 1)

    def test_missing_file_is_usage_error(self):
        p = self.run_cli("", "--file", str(HERE / "no_such_file.txt"))
        self.assertEqual(p.returncode, 2)


if __name__ == "__main__":
    unittest.main()

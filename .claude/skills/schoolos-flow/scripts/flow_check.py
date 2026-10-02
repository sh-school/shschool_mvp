#!/usr/bin/env python3
"""فحوصٌ حتميّةٌ لفلو منصّة المدرسة، بلا شبكةٍ ولا اعتمادٍ خارجيّ.

    python flow_check.py name "<عنوان الجلسة>" [...]
    python flow_check.py approval-line --file <ملفّ وصف الطلب>
    gh pr view <رقم> --json body -q .body | python flow_check.py approval-line

name: يطابق قاعدةَ `validate_registry.py` في حزمة المايسترو (TTSS، ≤ 40 بـlen())
      ويزيد عليها صيغةَ الجلسة المرنة في 04 (D-48م) وتنبيهَ التشكيل.
approval-line: يطابق تعبيرَ `evidence_pack.py` حرفيّاً.
رمزُ الخروج: 0 سليم، 1 مخالفة، 2 خطأُ استعمال.
"""

from __future__ import annotations

import argparse
import re
import sys

# الحدُّ من tabs.json → session_policy.serial.max_title_len
MAX_TITLE_LEN = 40
# وسومُ الاختصاص من tabs.json → specialties[].name_tag
KNOWN_TAGS = ("واجهة", "جدول", "إدارة")
# النصُّ الحرفيّ الذي تبحث عنه أدواتُ النشر (evidence_pack.py)
APPROVAL = re.compile(r"اعتُمد من المالك على 8500 — \d{4}-\d{2}-\d{2}")
# ما يشبه السطرَ ولا يطابقه: لتشخيص الخطأ الشائع
NEAR_APPROVAL = re.compile(r"اعت[ُ]?مد[^\n]{0,20}المالك[^\n]*")
# علاماتُ التشكيل العربيّة: تُعدّ في len() فتأكل من الحدّ
TASHKEEL = re.compile(r"[ً-ْٰ]")
FLEX_BODY = re.compile(r"^(?P<tag>[^:]+): (?P<task>.+) \((?P<code>[^()]+)\)$")


def check_name(title: str) -> tuple[list[str], list[str]]:
    """يعيد (مخالفات، تنبيهات) لعنوان جلسةٍ واحد."""
    errors: list[str] = []
    warnings: list[str] = []
    head, sep, rest = title.partition(" · ")
    if not (sep and len(head) == 4 and head.isdigit()):
        return [f"«{title}»: يبدأ برقمٍ من أربع خاناتٍ لاتينيّة ثمّ « · »"], warnings
    stage, serial = head[:2], int(head[2:])
    if not ("01" <= stage <= "08"):
        errors.append(f"المرحلة {stage} خارج 01..08")
    if serial < 1:
        errors.append("التسلسلُ داخل المرحلة يبدأ من 01")
    if len(title) > MAX_TITLE_LEN:
        errors.append(f"الطولُ {len(title)} > {MAX_TITLE_LEN} (يُعدّ العنوانُ كلُّه بالرقم والرمز والتشكيل) — اختصر المهمّةَ لا البنية")
    if not rest.strip():
        errors.append("بعد الرقم اسمٌ معبّر")
    marks = len(TASHKEEL.findall(title))
    if marks:
        warnings.append(f"فيه {marks} علامةَ تشكيلٍ تُعدّ في الحدّ؛ اكتبه بلا تشكيل")
    if stage == "04" and rest.strip():
        m = FLEX_BODY.match(rest.strip())
        if not m:
            errors.append("الجلسةُ المرنة: «04SS · <الاختصاص>: <مهمّةٌ قصيرة> (<الرمز>)»")
        elif m.group("tag").strip() not in KNOWN_TAGS:
            warnings.append(f"وسمُ الاختصاص «{m.group('tag').strip()}» غيرُ معروف ({'، '.join(KNOWN_TAGS)}) — تأكّد من 0301")
    return errors, warnings


def cmd_name(titles: list[str]) -> int:
    bad = 0
    for title in titles:
        errors, warnings = check_name(title.strip())
        state = "مخالف" if errors else "سليم"
        print(f"[{state}] «{title.strip()}» ({len(title.strip())} حرفاً)")
        for e in errors:
            print(f"  - {e}")
        for w in warnings:
            print(f"  ! {w}")
        bad += bool(errors)
    return 1 if bad else 0


def cmd_approval(text: str) -> int:
    found = APPROVAL.findall(text)
    if found:
        print(f"[سليم] السطرُ موجود: {found[0]}")
        return 0
    near = NEAR_APPROVAL.findall(text)
    print("[مخالف] لا سطرَ مطابقاً لـ«اعتُمد من المالك على 8500 — YYYY-MM-DD»")
    for line in near:
        print(f"  - شبيهٌ لا يطابق: «{line.strip()}» (تحقّق من الضمّة والشرطة الطويلة — والتاريخِ ISO بأرقامٍ لاتينيّة)")
    return 1


def main() -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")  # طرفيّةُ ويندوز لا تطبع العربيّة بترميزها الافتراضيّ
        except AttributeError:
            pass
    parser = argparse.ArgumentParser(description="فحوصُ فلو منصّة المدرسة")
    sub = parser.add_subparsers(dest="cmd", required=True)
    p_name = sub.add_parser("name", help="فحصُ عنوان جلسة")
    p_name.add_argument("titles", nargs="+")
    p_line = sub.add_parser("approval-line", help="فحصُ سطر الاعتماد في وصف الطلب")
    p_line.add_argument("--file", help="ملفُّ الوصف؛ بدونه يُقرأ من الدخل القياسيّ")
    args = parser.parse_args()
    if args.cmd == "name":
        return cmd_name(args.titles)
    if args.file:
        with open(args.file, encoding="utf-8") as fh:
            text = fh.read()
    else:
        text = sys.stdin.buffer.read().decode("utf-8")
    return cmd_approval(text)


if __name__ == "__main__":
    sys.exit(main())

"""scripts/pr_file_collision.py — تحذيرٌ حين يعدّل طلبا دمجٍ مفتوحان الملفّ نفسه.

سواط 2026-09-17: ثلاثةُ طلباتٍ مفتوحةٍ في آنٍ واحد عدّلت `templates/base/base.html`
بلا أن يعرف أصحابها بعضهم بعضاً — أوّلها يُدمج يُفسد تلقاء الاثنين الباقيين.
وقبله بساعات: طلبا دمجٍ (#299 و#303) نفّذا البندَ نفسَه من جلستين مختلفتين خلال
28 دقيقة، وأحدهما كان يحمل عيباً يوقف الهجرات صامتاً لو دُمج أوّلاً.

هذا تحذيرٌ لا حظر: تقاطعُ ملفّين ليس خطأً بذاته — قد يكونان تعديلين متكاملين،
أو ينسّق صاحباهما يدويّاً. الغرضُ إخبارَهما قبل أن يكتشفا التعارض في مراجعةٍ
لاحقة، لا منعُ الدمج.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys


def open_prs(repo: str) -> list[dict]:
    # وسائطُ ثابتةٌ بلا shell، وgh على PATH في مشغّلات GitHub.
    argv = [
        "gh",
        "pr",
        "list",
        "--repo",
        repo,
        "--state",
        "open",
        "--json",
        "number,headRefName,files",
    ]
    result = subprocess.run(argv, check=True, capture_output=True, text=True)  # noqa: S603
    return json.loads(result.stdout)


def collisions(pr_number: int, prs: list[dict]) -> list[tuple[int, str, list[str]]]:
    """(رقم الطلب الآخر، فرعه، الملفّات المشتركة) لكلّ طلبٍ يشترك في ملفٍّ."""
    current = next((p for p in prs if p["number"] == pr_number), None)
    if current is None:
        return []
    my_files = {f["path"] for f in current["files"]}
    if not my_files:
        return []

    found = []
    for other in prs:
        if other["number"] == pr_number:
            continue
        other_files = {f["path"] for f in other["files"]}
        overlap = sorted(my_files & other_files)
        if overlap:
            found.append((other["number"], other["headRefName"], overlap))
    return found


def main() -> int:
    repo = os.environ["REPO"]
    pr_number = int(os.environ["PR_NUMBER"])

    prs = open_prs(repo)
    hits = collisions(pr_number, prs)

    if not hits:
        print(f"لا تقاطعَ بين ملفّات #{pr_number} وأيّ طلبٍ مفتوحٍ آخر.")
        return 0

    for number, ref, files in hits:
        joined = "، ".join(f"`{f}`" for f in files)
        print(
            f"::warning::طلبُك يعدّل ملفّاتٍ يعدّلها طلبٌ مفتوحٌ آخر "
            f"#{number} ({ref}): {joined} — نسّق مع صاحبه قبل الدمج، أو "
            f"تحقّق من عدم التعارض بعد دمج أحدكما."
        )
    return 0  # تحذيرٌ لا حظر — لا يُسقط البوّابة أبداً


if __name__ == "__main__":
    sys.exit(main())

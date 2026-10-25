#!/usr/bin/env python3
"""سقفُ خوادم الجلسات الحيّة (W-20261016-009): يعدّ حاويات الويب للجلسات ويرفض التشغيل الرابع، ويُطفئ الخاملة.

ضغطُ ذاكرة Docker (سقفُ WSL نحو 4 غيغا) عطّل المحرّكَ مرّتين من جلساتٍ حيّةٍ كثيرة. يمرّ به كلُّ `make session`:

    python scripts/session_cap.py --project schoolos-<شجرتك>   فحصُ التشغيل (يُطفئ الخاملة إن بلغ السقف ثم يعيد العدّ)
    python scripts/session_cap.py --reap [--dry-run]            إطفاءُ الخاملة فقط (stop لا rm)

القواعد: «جلسة حيّة» = حاويةُ ويب باسم schoolos-<شجرة>-web-1 تعمل. السقف 3. «خاملة» = لا طلبَ في سجلّها آخرَ 30 دقيقةً
(تُهمَل أسطرُ فحص الصحّة health). الإطفاءُ stop لمشروع الجلسة وحده (لا يحذف قاعدةً ولا حجماً). لا يُمَسّ أبداً:
المعاينةُ المركزيّة (schoolos-main-preview-*) وحاوياتُ shschool-dev-* وأيُّ حاويةٍ خارج نمط الجلسات. وما تعذّر قياسُه
(docker غائب) يُطبع «غير مقيس» ولا يمنع التشغيل ولا يُطفئ شيئاً.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys

CAP = 3
IDLE_MINUTES = 30
SESSION_WEB = re.compile(r"^(schoolos-(?!main-preview-)[\w.-]+)-web-1$")
UNMEASURED = "غير مقيس"
ALLOWED = ("ps", "logs", "stop")


def run(args: list[str]) -> str | None:
    """يشغّل docker (ps وlogs وstop فقط)؛ None عند غيابه أو فشله."""
    if len(args) < 2 or args[0] != "docker" or args[1] not in ALLOWED:
        raise PermissionError(f"أمرٌ خارج المسموح: {args[:2]}")
    try:
        r = subprocess.run(args, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=60, check=False)  # noqa: S603
    except (OSError, subprocess.TimeoutExpired):
        return None
    return (r.stdout + r.stderr) if r.returncode == 0 and args[1] == "logs" else (r.stdout if r.returncode == 0 else None)


def live_sessions(ps_out: str | None) -> list[str] | None:
    """مشاريعُ الجلسات الحيّة من مخرج `docker ps --format {{.Names}}`؛ None إن لم يُقَس."""
    if ps_out is None:
        return None
    found = set()
    for name in ps_out.split():
        m = SESSION_WEB.match(name.strip())
        if m:
            found.add(m.group(1))
    return sorted(found)


def is_idle(logs_out: str | None) -> bool | None:
    """True إن خلا سجلُّ آخر 30 دقيقةً من غير فحص الصحّة؛ None إن لم يُقَس."""
    if logs_out is None:
        return None
    return not any(line.strip() and "health" not in line.lower() for line in logs_out.splitlines())


def reap(projects: list[str], runner=run, dry_run: bool = False) -> list[str]:
    """يُطفئ (stop) مشاريعَ الجلسات الخاملة؛ يعيد ما أُطفئ (أو ما كان سيُطفأ في dry-run)."""
    stopped = []
    for proj in projects:
        if not SESSION_WEB.match(f"{proj}-web-1"):
            continue  # حمايةٌ: لا مشروعَ خارج نمط الجلسات
        if is_idle(runner(["docker", "logs", "--since", f"{IDLE_MINUTES}m", f"{proj}-web-1"])) is not True:
            continue
        if dry_run:
            stopped.append(proj)
            continue
        ids = runner(["docker", "ps", "-q", "--filter", f"label=com.docker.compose.project={proj}"])
        if ids and ids.split() and runner(["docker", "stop", *ids.split()]) is not None:
            stopped.append(proj)
    return stopped


def check(project: str, runner=run) -> tuple[int, str]:
    """(رمزُ الخروج، الرسالة): 0 يسمح، 1 يرفض. مشروعُك الحيُّ لا يُحسب عليك (إعادةُ تشغيل)."""
    live = live_sessions(runner(["docker", "ps", "--format", "{{.Names}}"]))
    if live is None:
        return 0, f"{UNMEASURED}: docker غير متاح — لا فحصَ للسقف"
    others = [p for p in live if p != project]
    if len(others) < CAP:
        return 0, f"الجلسات الحيّة {len(others)} من {CAP} — يُسمح"
    freed = reap(others, runner)
    if freed:
        live = live_sessions(runner(["docker", "ps", "--format", "{{.Names}}"])) or []
        if len([p for p in live if p != project]) < CAP:
            return 0, f"أُطفئت {len(freed)} خاملة ({'، '.join(freed)}) — يُسمح"
    return 1, (
        f"رُفض: بلغت الجلساتُ الحيّةُ السقفَ ({CAP}) ولا خاملةَ تُطفأ: {'، '.join(others)}. "
        "أطفئ جلسةً بـ`make session-down` من شجرتها ثم أعِد المحاولة (ذاكرةُ Docker محدودة)."
    )


def main(argv=None) -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--project", help="مشروعُ جلستك (schoolos-<الشجرة>)")
    ap.add_argument("--reap", action="store_true", help="أطفئ الخاملة فقط")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args(argv)
    if a.reap:
        live = live_sessions(run(["docker", "ps", "--format", "{{.Names}}"]))
        if live is None:
            print(f"{UNMEASURED}: docker غير متاح")
            return 0
        done = reap(live, dry_run=a.dry_run)
        print(("كان سيُطفأ: " if a.dry_run else "أُطفئ: ") + ("، ".join(done) or "لا شيء"))
        return 0
    if not a.project:
        ap.error("--project مطلوب لفحص التشغيل")
    code, msg = check(a.project)
    print(msg)
    return code


if __name__ == "__main__":
    raise SystemExit(main())

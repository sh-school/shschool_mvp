#!/usr/bin/env python3
"""فحصُ صحّة البيئة المحلّيّة: حاوياتٌ ومنافذُ و`/health/` واتصالُ دور التطبيق (W-20261017-017).

يقرأ ولا يغيّر افتراضيّاً. يطبع لكلّ حاويةِ جلسةٍ حالتَها، ثمّ هل يستجيب `/health/` على منفذها
المنشور (ومنه 8500)، ثمّ هل يتّصل دورُ التطبيق `shschool_app` بقاعدته من داخل الحاوية.
لا يطبع كلمةَ الدور ولا أيَّ قيمةٍ من بيئة الحاوية: «يتّصل / لا يتّصل» مع سببٍ مصنَّفٍ فقط.

    python scripts/env_health.py                 # قراءةٌ فقط
    python scripts/env_health.py --fix NAME ...  # يعيد تشغيل الحاويات المسمّاة وحدَها (schoolos-*)

لا يمسّ الإنتاجَ ولا Railway، ولا يشغّل `preview.sh up/down`، ولا يلمس حاويةَ قاعدة الحزمة الأصليّة.
الخروج: 0 سليم، 1 عطلٌ مكتشف، 2 خطأُ استعمال.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
import urllib.error
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass, field

# بادئةُ حاويات الجلسات والمعاينة؛ وحدَها ما يجوز لـ--fix إعادةُ تشغيله.
SESSION_PREFIX = "schoolos-"
# حاويةُ القاعدة المشتركة: تُفحص ولا تُعاد (قاعدةُ كلّ الأشجار).
DB_CONTAINER = "shschool-dev-db"

Runner = Callable[[list[str]], tuple[int, str]]

# يُنفَّذ داخل حاوية الويب؛ لا يطبع إلا رمزاً مصنَّفاً، ولا يطبع نصَّ الخطأ (قد يحمل اسمَ المضيف).
_ROLE_PROBE = (
    "import os,psycopg2\n"
    "try:\n"
    " psycopg2.connect(host=os.environ['DB_HOST'],port=os.environ['DB_PORT'],dbname=os.environ['DB_NAME'],"
    "user='shschool_app',password=os.environ.get('APP_DB_PASSWORD',''),connect_timeout=3).close();print('OK')\n"
    "except Exception as e:\n"
    " m=str(e).lower()\n"
    " print('AUTH' if 'password authentication' in m else 'NODB' if 'does not exist' in m else "
    "'NOROUTE' if ('could not connect' in m or 'timeout' in m or 'refused' in m) else 'OTHER')\n"
)


@dataclass
class Container:
    name: str
    status: str
    ports: str

    @property
    def running(self) -> bool:
        return self.status.startswith("Up")

    @property
    def unhealthy(self) -> bool:
        return "unhealthy" in self.status

    @property
    def restarting(self) -> bool:
        return self.status.startswith("Restarting")

    def published_ports(self) -> list[int]:
        """المنافذُ المنشورة على المضيف (0.0.0.0:8500->8000/tcp ← 8500)، بلا تكرار IPv6."""
        return sorted({int(p) for p in re.findall(r":(\d+)->", self.ports)})


@dataclass
class Finding:
    where: str
    problem: str
    hint: str = ""


@dataclass
class Report:
    findings: list[Finding] = field(default_factory=list)
    lines: list[str] = field(default_factory=list)

    def add(self, where: str, problem: str, hint: str = "") -> None:
        self.findings.append(Finding(where, problem, hint))


def default_runner(cmd: list[str]) -> tuple[int, str]:
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=60, check=False)  # noqa: S603
    except (OSError, subprocess.TimeoutExpired) as exc:
        return 127, type(exc).__name__
    return proc.returncode, (proc.stdout or "") + (proc.stderr or "")


def parse_ps(output: str) -> list[Container]:
    """يحلّل `docker ps -a --format '{{.Names}}\\t{{.Status}}\\t{{.Ports}}'`."""
    found = []
    for line in output.splitlines():
        parts = line.split("\t")
        if len(parts) >= 2 and parts[0].strip():
            found.append(
                Container(
                    parts[0].strip(), parts[1].strip(), parts[2].strip() if len(parts) > 2 else ""
                )
            )
    return found


def list_containers(run: Runner) -> tuple[list[Container], str | None]:
    code, out = run(["docker", "ps", "-a", "--format", "{{.Names}}\t{{.Status}}\t{{.Ports}}"])
    if code != 0:
        return [], "docker لا يستجيب (هل Docker Desktop يعمل؟) — لا أعيد تشغيله من هنا"
    return parse_ps(out), None


def check_container(c: Container, report: Report) -> None:
    if c.restarting:
        report.add(c.name, "الحاويةُ في إعادةِ تشغيلٍ متكرّرة", "docker logs --tail 40 " + c.name)
    elif not c.running:
        report.add(c.name, "الحاويةُ متوقّفة (" + c.status + ")", "--fix " + c.name)
    elif c.unhealthy:
        report.add(c.name, "الحاويةُ تعمل لكنّ فحصَ صحّتها فاشل (unhealthy)", "--fix " + c.name)


def check_db_port(containers: list[Container], report: Report) -> None:
    db = next((c for c in containers if c.name == DB_CONTAINER), None)
    if db is None:
        report.add(DB_CONTAINER, "حاويةُ قاعدة البيانات غير موجودة")
    elif not db.running:
        report.add(
            DB_CONTAINER,
            "حاويةُ قاعدة البيانات متوقّفة (" + db.status + ")",
            "تشغيلها للمالك أو لجلسة النشر",
        )
    elif 5433 not in db.published_ports():
        report.add(
            DB_CONTAINER,
            "منفذُ 5433 غير ممرَّر إلى المضيف",
            "الحاوياتُ تصل إليها عبر host.docker.internal:5433",
        )


def http_ok(url: str, opener: Callable[..., object] = urllib.request.urlopen) -> tuple[bool, str]:
    try:
        resp = opener(url, timeout=5)  # type: ignore[operator]
        code = getattr(resp, "status", 200)
        return code == 200, f"HTTP {code}"
    except urllib.error.HTTPError as exc:
        return False, f"HTTP {exc.code}"
    except (urllib.error.URLError, OSError, TimeoutError) as exc:
        return False, type(exc).__name__


def check_health(c: Container, report: Report, probe: Callable[[str], tuple[bool, str]]) -> None:
    for port in c.published_ports():
        ok, detail = probe(f"http://localhost:{port}/health/")
        if not ok:
            report.add(
                f"{c.name}:{port}",
                f"/health/ لا يستجيب ({detail})",
                "راجع سجلَّ الحاوية؛ ثمّ اتصالَ الدور أدناه",
            )


_ROLE_PROBLEMS = {
    "AUTH": (
        "كلمةُ shschool_app في بيئة الحاوية لا تطابق الدورَ في القاعدة",
        "قارن بصمة APP_DB_PASSWORD في .env بالدور (دون عرضها)",
    ),
    "NODB": ("قاعدةُ DB_NAME غير موجودة", "bash scripts/session-db.sh في شجرتها"),
    "NOROUTE": ("لا طريقَ إلى القاعدة من الحاوية", "تحقّق من تمرير 5433 وhost.docker.internal"),
    "OTHER": ("فشلٌ في الاتصال بسببٍ غير مصنَّف", "docker logs ثمّ psycopg2.connect بلا إسكات الخطأ"),
}


def classify_role_output(output: str) -> str:
    """رمزٌ واحدٌ من OK/AUTH/NODB/NOROUTE/OTHER من آخر سطرٍ مطبوع؛ أيُّ شيءٍ آخر OTHER."""
    last = output.strip().splitlines()[-1].strip() if output.strip() else ""
    return last if last in ("OK", *_ROLE_PROBLEMS) else "OTHER"


def check_role(c: Container, report: Report, run: Runner) -> str:
    if not c.running:
        return "SKIP"
    code, out = run(["docker", "exec", c.name, "python", "-c", _ROLE_PROBE])
    if code != 0:
        # لا يوجد python/psycopg2 أو الحاويةُ ليست ويباً (عاملٌ مثلاً): لا يُعدّ عطلاً هنا.
        return "SKIP"
    kind = classify_role_output(out)
    if kind != "OK":
        problem, hint = _ROLE_PROBLEMS[kind]
        report.add(c.name, problem, hint)
    return kind


def is_session_web(c: Container) -> bool:
    return c.name.startswith(SESSION_PREFIX) and c.name.endswith("-web-1")


def collect(run: Runner, probe: Callable[[str], tuple[bool, str]] = http_ok) -> Report:
    report = Report()
    containers, err = list_containers(run)
    if err:
        report.add("docker", err)
        return report
    check_db_port(containers, report)
    for c in (c for c in containers if c.name.startswith(SESSION_PREFIX)):
        check_container(c, report)
        if is_session_web(c) and c.running:
            check_health(c, report, probe)
            role = check_role(c, report, run)
            report.lines.append(
                f"{c.name}: {c.status} — اتصالُ الدور: {'يتّصل' if role == 'OK' else 'لا يتّصل' if role != 'SKIP' else 'لم يُفحص'}"
            )
        else:
            report.lines.append(f"{c.name}: {c.status}")
    return report


def fix(names: list[str], run: Runner) -> list[str]:
    """يعيد تشغيل الحاويات المسمّاة وحدَها، ويرفض ما ليس بادئتُه schoolos-؛ يطبع ما فعله."""
    done = []
    for name in names:
        if not name.startswith(SESSION_PREFIX):
            done.append(f"رفضتُ {name}: --fix لحاويات {SESSION_PREFIX}* وحدَها")
            continue
        code, _ = run(["docker", "restart", name])
        done.append(f"أعدتُ تشغيل {name}" if code == 0 else f"فشلت إعادةُ تشغيل {name}")
    return done


def render(report: Report) -> str:
    out = list(report.lines)
    if not report.findings:
        out.append("✔ لا عطلَ مكتشف")
    for f in report.findings:
        out.append(f"✘ {f.where}: {f.problem}" + (f"  ← {f.hint}" if f.hint else ""))
    return "\n".join(out)


def main(argv: list[str] | None = None, run: Runner = default_runner) -> int:
    parser = argparse.ArgumentParser(description="فحصُ صحّة البيئة المحلّيّة (قراءةٌ افتراضاً)")
    parser.add_argument(
        "--fix", nargs="+", metavar="NAME", help="يعيد تشغيل هذه الحاويات (schoolos-*) وحدَها"
    )
    args = parser.parse_args(argv)
    if args.fix:
        print("\n".join(fix(args.fix, run)))
        return 0
    report = collect(run)
    print(render(report))
    return 1 if report.findings else 0


if __name__ == "__main__":
    sys.exit(main())

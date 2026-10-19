#!/usr/bin/env python3
"""قاعدةُ اختبارٍ مهجَّرةٌ تُعاد استعمالها لكلّ شجرة، وتُبطَل ببصمة الهجرات (W-20261016-014).

كان كلُّ تشغيلِ pytest يبني قاعدةَ الاختبار من كلّ الهجرات (>500 ث). هنا تُهجَّر مرّةً وتُحفظ بصمةُ ملفّات
الهجرات في تعليق القاعدة نفسِها؛ فإن طابقت البصمةُ أُعيد الاستعمال (`--reuse-db`)، وإلا حُذفت وأُعيد البناء.
القاعدةُ هي `TEST_DB_NAME` (لكلّ شجرةٍ اسمُها `test_ss_<slug>`) فلا تُشارَك بين شجرتين.

الاستعمال:  python scripts/session_test_db.py   (يطبع: reuse | rebuild)
"""

from __future__ import annotations

import hashlib
import os
import subprocess
import sys
from pathlib import Path

import psycopg2
from psycopg2 import sql

ROOT = Path(__file__).resolve().parent.parent
_SKIP = {".git", "node_modules", "venv", ".venv", "staticfiles", ".claude"}


def migrations_fingerprint(root: Path = ROOT) -> str:
    """تجزئةُ مسارات ومحتوى كلّ ملفّ هجرةٍ — أيُّ تغييرٍ أو إضافةٍ أو حذفٍ يغيّرها."""
    h = hashlib.sha256()
    files = sorted(
        p for p in root.rglob("migrations/*.py") if not (_SKIP & set(p.relative_to(root).parts))
    )
    for p in files:
        h.update(p.relative_to(root).as_posix().encode())
        h.update(b"\0")
        h.update(p.read_bytes())
        h.update(b"\0")
    return h.hexdigest()


def decide(existing_comment: str | None, fingerprint: str) -> str:
    """`reuse` إن طابقت بصمةُ القاعدة الحاليّةُ بصمةَ الملفّات، وإلا `rebuild`."""
    return "reuse" if existing_comment == f"migrations:{fingerprint}" else "rebuild"


def _connect(dbname: str):
    return psycopg2.connect(
        dbname=dbname,
        user=os.environ.get("TEST_DB_USER", "test_user"),
        password=os.environ.get("TEST_DB_PASSWORD", "test_pass"),
        host=os.environ.get("TEST_DB_HOST", "localhost"),
        port=os.environ.get("TEST_DB_PORT", "5432"),
    )


def current_comment(name: str) -> str | None:
    conn = _connect("postgres")
    try:
        with conn.cursor() as cur:
            cur.execute("select shobj_description(oid, 'pg_database') from pg_database where datname = %s", (name,))
            row = cur.fetchone()
            return row[0] if row else None
    finally:
        conn.close()


def rebuild(name: str, fingerprint: str) -> None:
    conn = _connect("postgres")
    conn.autocommit = True
    with conn.cursor() as cur:
        cur.execute(sql.SQL("DROP DATABASE IF EXISTS {}").format(sql.Identifier(name)))
        cur.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
    conn.close()
    env = dict(os.environ, DJANGO_SETTINGS_MODULE="shschool.settings.testing", TEST_DB_NAME=name)
    subprocess.run([sys.executable, "manage.py", "migrate", "--noinput"], cwd=ROOT, env=env, check=True)  # noqa: S603
    conn = _connect("postgres")
    conn.autocommit = True
    with conn.cursor() as cur:
        cur.execute(
            sql.SQL("COMMENT ON DATABASE {} IS {}").format(sql.Identifier(name), sql.Literal(f"migrations:{fingerprint}"))
        )
    conn.close()


def main() -> int:
    name = os.environ.get("TEST_DB_NAME", "test_db")
    fp = migrations_fingerprint()
    action = decide(current_comment(name), fp)
    if action == "rebuild":
        rebuild(name, fp)
    print(action)
    return 0


if __name__ == "__main__":
    sys.exit(main())

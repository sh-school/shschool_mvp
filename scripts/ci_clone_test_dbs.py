#!/usr/bin/env python3
"""ينسخ قاعدةَ الاختبار المهجَّرة إلى قاعدةِ كلّ عاملِ xdist بدل بنائها بالهجرات في كلٍّ منهم (W-20261016-029).

الاستعمال (بعد `python manage.py migrate` على القاعدة الرئيسة):  python scripts/ci_clone_test_dbs.py [عدد العمّال]

كان كلُّ عاملٍ يبني قاعدتَه بالهجرات (~190–400 ث، أربعةٌ معاً على الأنوية نفسِها) وتُنسب كلفتُها لأوّل اختبارٍ
فيه (انظر scripts/ci_shard_weights.py). هجرةٌ واحدة (~150 ث) ثمّ `CREATE DATABASE … TEMPLATE` (ثوانٍ) تُغني عن ذلك،
ويُشغَّل pytest بـ`--reuse-db` فيجد القواعدَ `<الاسم>_gw0…` جاهزةً. لا حالةَ مشتركة: لكلّ عاملٍ نسختُه.
عددٌ أقلُّ من العمّال الفعليّين ليس خطأً: العاملُ بلا نسخةٍ يبني قاعدتَه بنفسه كما كان.
"""

from __future__ import annotations

import os
import sys

import psycopg2
from psycopg2 import sql


def worker_names(template: str, workers: int) -> list[str]:
    """أسماءُ قواعد العمّال كما يشتقّها pytest-django: `<الاسم>_gw<ن>`."""
    return [f"{template}_gw{i}" for i in range(workers)]


def clone(template: str, workers: int, connect) -> list[str]:
    conn = connect()
    conn.autocommit = True
    made = []
    with conn.cursor() as cur:
        for name in worker_names(template, workers):
            cur.execute(sql.SQL("DROP DATABASE IF EXISTS {}").format(sql.Identifier(name)))
            cur.execute(
                sql.SQL("CREATE DATABASE {} TEMPLATE {}").format(sql.Identifier(name), sql.Identifier(template))
            )
            made.append(name)
    conn.close()
    return made


def _connect():
    return psycopg2.connect(
        dbname="postgres",
        user=os.environ.get("TEST_DB_USER", "test_user"),
        password=os.environ.get("TEST_DB_PASSWORD", "test_pass"),  # pragma: allowlist secret
        host=os.environ.get("TEST_DB_HOST", "localhost"),
        port=os.environ.get("TEST_DB_PORT", "5432"),
    )


def main(argv: list[str]) -> int:
    template = os.environ.get("TEST_DB_NAME", "test_db")
    workers = int(argv[1]) if len(argv) > 1 else (os.cpu_count() or 1)
    made = clone(template, workers, _connect)
    print(f"نُسخت {len(made)} قاعدةً من {template}: {', '.join(made)}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))

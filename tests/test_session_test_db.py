"""بصمةُ الهجرات تُبطل قاعدةَ الاختبار المعاد استعمالها (W-20261016-014)."""

from __future__ import annotations

from pathlib import Path

from scripts import session_test_db as m


def _tree(tmp_path: Path, body: str = "x = 1\n") -> Path:
    mig = tmp_path / "app" / "migrations"
    mig.mkdir(parents=True)
    (mig / "0001_initial.py").write_text(body, encoding="utf-8")
    return tmp_path


def test_unchanged_migrations_give_same_fingerprint_and_reuse(tmp_path):
    root = _tree(tmp_path)
    fp = m.migrations_fingerprint(root)
    assert fp == m.migrations_fingerprint(root)
    assert m.decide(f"migrations:{fp}", fp) == "reuse"


def test_changed_or_new_migration_invalidates(tmp_path):
    root = _tree(tmp_path)
    before = m.migrations_fingerprint(root)
    (root / "app" / "migrations" / "0001_initial.py").write_text("x = 2\n", encoding="utf-8")
    edited = m.migrations_fingerprint(root)
    assert edited != before
    (root / "app" / "migrations" / "0002_more.py").write_text("y = 1\n", encoding="utf-8")
    added = m.migrations_fingerprint(root)
    assert added != edited
    assert m.decide(f"migrations:{before}", added) == "rebuild"


def test_missing_database_or_comment_rebuilds():
    assert m.decide(None, "abc") == "rebuild"
    assert m.decide("other", "abc") == "rebuild"


def test_session_test_script_prints_unmeasured_explicitly():
    text = (Path(__file__).resolve().parent.parent / "scripts" / "session-test.sh").read_text(
        encoding="utf-8"
    )
    assert "غير مقيس" in text and "--reuse-db" in text

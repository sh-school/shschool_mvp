"""سطرُ استخدام provision_rls_app_role.sql لا يوصي باقتباسٍ زائدٍ لكلمة المرور (W-20261017-016، قرار المالك 2026-10-17).

السكربت يقتبس بنفسه (`:'app_password'`)، فمثالٌ يمرّر الكلمةَ بعلامتي اقتباسٍ يحفظها بهما فيسقط اتصالُ المعاينة.
فحصٌ نصّيٌّ بلا قاعدة بيانات ولا psql.
"""

from __future__ import annotations

import re
from pathlib import Path

SQL = Path(__file__).resolve().parent.parent / "scripts" / "provision_rls_app_role.sql"


def _lines() -> list[str]:
    return SQL.read_text(encoding="utf-8").splitlines()


def test_the_usage_example_passes_the_password_without_extra_quotes():
    examples = [ln for ln in _lines() if "-v app_password" in ln]
    assert examples, "لم أجد مثالَ الاستخدام — تغيّر الملفّ؟ حدِّث الاختبار"
    for ln in examples:
        assert re.search(r"-v app_password=[^\s\"']+", ln), ln
        assert not re.search(r"app_password=[\"']", ln), ln


def test_no_comment_recommends_quoting_the_password_value():
    for ln in _lines():
        if ln.lstrip().startswith("--"):
            assert not re.search(r"app_password=[\"']", ln), ln


def test_the_script_itself_still_quotes_the_variable_once():
    """الاقتباسُ الوحيدُ في السكربت: format(%L) على :'app_password' — لا يُلمس من أجل التعليمات."""
    body = "\n".join(ln for ln in _lines() if not ln.lstrip().startswith("--"))
    assert ":'app_password'" in body

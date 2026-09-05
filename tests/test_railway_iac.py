"""`.railway/railway.ts` — ملفُّ Infrastructure as Code لِـRailway.

حتّى يُطبَّق على الإنتاج (`railway config apply` بيد المستخدم) يبقى `railway.json`
و`railway.worker.json` مصدرَ الحقيقة الذي يقرؤه Railway. هذا الاختبار يضمن أنّ الملفّين
لا يفترقان: ما يقوله الـIaC عن كلّ خدمةٍ هو ما يقوله ملفُّ Config as Code الخاصّ بها.

ويضمن ما هو أهمّ في مستودعٍ عامّ: لا قيمةَ متغيّرٍ في الملفّ — كلُّ متغيّرٍ `preserve()`.
"""

import json
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
IAC = ROOT / ".railway" / "railway.ts"


@pytest.fixture(scope="module")
def iac() -> str:
    return IAC.read_text(encoding="utf-8")


def _service_block(source: str, name: str) -> str:
    match = re.search(rf'service\("{re.escape(name)}",\s*\{{(.*?)\n  \}}\);', source, re.DOTALL)
    assert match, f"الخدمة {name} غير معرَّفة في {IAC.name}"
    return match.group(1)


def _string_option(block: str, key: str) -> str | None:
    match = re.search(rf'\b{key}:\s*"([^"]*)"', block)
    return match.group(1) if match else None


def _number_option(block: str, key: str) -> int | None:
    match = re.search(rf"\b{key}:\s*(\d+)", block)
    return int(match.group(1)) if match else None


def test_iac_manages_the_whole_project_not_a_partial(iac):
    # `partial` يحصر الخطّة في خدمةٍ واحدة ويترك الباقي بلا حماية — ممنوع هنا.
    assert "export const partial" not in iac
    for resource in ('postgres("Postgres")', 'redis("Redis")', 'bucket("Postgres-PITR"'):
        assert resource in iac, f"موردٌ غيرُ مذكورٍ سيحذفه apply: {resource}"


@pytest.mark.parametrize(
    ("service_name", "cac_file"),
    [("shschool_mvp", "railway.json"), ("celery-worker", "railway.worker.json")],
)
def test_iac_matches_config_as_code(iac, service_name, cac_file):
    cac = json.loads((ROOT / cac_file).read_text(encoding="utf-8"))
    block = _service_block(iac, service_name)

    assert _string_option(block, "start") == cac["deploy"]["startCommand"]
    assert _string_option(block, "healthcheck") == cac["deploy"].get("healthcheckPath")
    assert _number_option(block, "healthcheckTimeout") == cac["deploy"].get("healthcheckTimeout")

    assert cac["build"]["builder"] == "DOCKERFILE" and "DOCKER_BUILD" in block
    assert cac["deploy"]["restartPolicyType"] == "ON_FAILURE" and "RESTART_ON_FAILURE" in block
    assert cac["deploy"]["restartPolicyMaxRetries"] == 3
    assert 'builder: "DOCKERFILE", dockerfilePath: "Dockerfile"' in iac
    assert 'restartPolicyType: "ON_FAILURE", restartPolicyMaxRetries: 3' in iac


def test_iac_never_carries_variable_values(iac):
    # المستودع عامّ: الأسماء تُسرَد والقيمُ تبقى في Railway عبر preserve().
    for block_name in ("SHARED_VARIABLES", "WEB_VARIABLES", "WORKER_VARIABLES"):
        match = re.search(rf"const {block_name} = \[(.*?)\] as const;", iac, re.DOTALL)
        assert match, block_name
        entries = re.findall(r'"([^"]*)"', match.group(1))
        assert entries, block_name
        assert all(re.fullmatch(r"[A-Z][A-Z0-9_]*", e) for e in entries), entries

    assert "preserve()" in iac
    # لا سطرَ يُسند قيمةً إلى اسمِ متغيّرٍ بيئيّ.
    assert not re.search(
        r'\b[A-Z][A-Z0-9_]{3,}:\s*"[^"]+"', iac.replace('builder: "DOCKERFILE"', "")
    )

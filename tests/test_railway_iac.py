"""`.railway/railway.ts` — ملفُّ Infrastructure as Code لِـRailway، مصدرُ الحقيقة الوحيد.

يحرس ما لا يُرى في مراجعة الفرق: أنّ الملفّ يصف المشروعَ كاملاً (فـ`apply` يحذف ما لا
يذكره)، وأنّ كلَّ متغيّرٍ `preserve()` بلا قيمة (المستودع عامّ)، وأنّ ملفّي Config as Code
القديمين لم يعودا — Railway يقرأ `railway.json` افتراضاً إن وُجد ويقدّمه على الإعدادات.
"""

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


def test_config_as_code_files_are_gone():
    # وجودُ railway.json يُعيد قراءةَ الإعدادات القديمة ويتقدّم على ما في Railway.
    for legacy in ("railway.json", "railway.worker.json", "railway.toml"):
        assert not (
            ROOT / legacy
        ).exists(), f"{legacy} يجب ألّا يعود — الحقيقة في .railway/railway.ts"


def test_iac_manages_the_whole_project_not_a_partial(iac):
    # `partial` يحصر الخطّة في خدمةٍ واحدة ويترك الباقي بلا حماية — ممنوع هنا.
    assert "export const partial" not in iac
    for resource in ('postgres("Postgres")', 'redis("Redis")', 'bucket("Postgres-PITR"'):
        assert resource in iac, f"موردٌ غيرُ مذكورٍ سيحذفه apply: {resource}"


def test_web_service_is_declared_as_deployed(iac):
    web = _service_block(iac, "shschool_mvp")
    assert 'start: "bash scripts/railway-release.sh"' in web
    assert 'healthcheck: "/health/"' in web
    assert "healthcheckTimeout: 100" in web
    assert "build: DOCKER_BUILD" in web and "deploy: RESTART_ON_FAILURE" in web
    assert "source: github(REPO)" in web


def test_worker_service_has_no_http_healthcheck(iac):
    worker = _service_block(iac, "celery-worker")
    assert 'start: "bash scripts/railway-worker.sh"' in worker
    assert "healthcheck" not in worker
    assert "build: DOCKER_BUILD" in worker and "deploy: RESTART_ON_FAILURE" in worker


def test_build_and_restart_policy(iac):
    assert 'builder: "DOCKERFILE", dockerfilePath: "Dockerfile"' in iac
    assert "restartPolicyMaxRetries: 3" in iac
    # ON_FAILURE افتراضُ Railway ويخزّنه فارغاً: ذكرُه يجعل الخطّة «to change» إلى الأبد.
    assert "restartPolicyType" not in iac.split("*/", 1)[1]


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
    assert not re.search(r'[A-Z][A-Z0-9_]{3,}:\s*"[^"]+"', iac.replace('builder: "DOCKERFILE"', ""))

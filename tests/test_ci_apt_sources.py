"""[CI] كل `apt-get update` في المهامّ يُسقط مستودعات الطرف الثالث قبله.

صورة المنصّة تشحن مستودعات Microsoft/azure-cli ولا نستعمل منها حزمةً واحدة.
وفي ٢٨ أغسطس ٢٠٢٦ سقط توقيعها فأعادت `403`، فسقط `apt-get update` كلّه بالرمز
١٠٠ — فسقط «فحص أمن النشر»، فسقط «ملخّص بوابة الجودة»، فحُجب الدمج لسببٍ لا
صلة له بالشيفرة المطروحة.

    E: The repository 'https://packages.microsoft.com/repos/azure-cli noble
       InRelease' is no longer signed.

والخطر أن هذا يبدو فشلاً أمنياً في لوحة الفحوص، فيُغري بتخفيف البوابة كي
تُعبَر. وإسقاط المستودع يترك أرشيف أوبنتو وحده — ولا يمسّ `pgdg` الذي تضيفه
وظيفتا النسخ الاحتياطي عمداً للحصول على عميل PostgreSQL 18.

والحارس هنا هو الحماية الحقيقية: سبعة عشر موضعاً اليوم، والثامن عشر الذي
يُكتب غداً سينساه كاتبه ما لم يُمنع.
"""

import pathlib

import yaml

WORKFLOWS = pathlib.Path(".github/workflows")
ACTIONS = pathlib.Path(".github/actions")

#: إسقاط المستودعات التي تشحنها الصورة ولا نستعملها.
HARDENING = "rm -f /etc/apt/sources.list.d/*microsoft*"


def _run_blocks():
    """كل نصّ `run` في كل خطوة من كل وظيفة وكلّ إجراءٍ مركّب، مع موضعه."""
    # الإجراءاتُ المركّبة المحلّيّة (native-postgres يثبّت redis وpostgres 18 بـapt) — خطواتُها ليست تحت `jobs`
    for f in sorted(ACTIONS.glob("*/action.yml")):
        doc = yaml.safe_load(f.read_text(encoding="utf-8"))
        for i, step in enumerate((doc.get("runs") or {}).get("steps") or []):
            run = step.get("run")
            if isinstance(run, str):
                yield f"{f.parent.name}/action.yml:step[{i}]", run
    for f in sorted(WORKFLOWS.glob("*.yml")):
        doc = yaml.safe_load(f.read_text(encoding="utf-8"))
        for job_name, job in (doc.get("jobs") or {}).items():
            for i, step in enumerate(job.get("steps") or []):
                run = step.get("run")
                if isinstance(run, str):
                    yield f"{f.name}:{job_name}:step[{i}]", run


def test_workflows_exist():
    """حارسٌ يمسح لا شيء يمرّ دائماً."""
    assert list(_run_blocks())


def test_every_apt_update_drops_the_unused_third_party_repos():
    offenders = [
        where for where, run in _run_blocks() if "apt-get update" in run and HARDENING not in run
    ]

    assert not offenders, f"`apt-get update` بلا تحصين في: {offenders}"


def test_the_hardening_runs_before_the_update_not_after():
    """الترتيب هو الفائدة كلّها — إسقاطٌ بعد التحديث لا يمنع سقوطه."""
    late = []
    for where, run in _run_blocks():
        if "apt-get update" not in run or HARDENING not in run:
            continue
        if run.index(HARDENING) > run.index("apt-get update"):
            late.append(where)

    assert not late, f"التحصين يأتي بعد التحديث في: {late}"


def test_the_postgres_repository_is_not_dropped():
    """وظيفتا النسخ الاحتياطي تضيفان `pgdg` عمداً — والإسقاط لا يطاله."""
    adders = [where for where, run in _run_blocks() if "pgdg.list" in run]

    assert adders, "لم يعد أحدٌ يضيف مستودع PostgreSQL — تحقّق قبل حذف هذا الحارس"
    for where, run in _run_blocks():
        if HARDENING in run:
            assert "pgdg" not in run.split(HARDENING)[1].split("\n")[0], where


def test_the_backup_workflow_is_hardened_too():
    """تُجدوَل بلا مراجعةٍ بشرية — فسقوطها لا يراه أحد حتى تُطلب نسخة."""
    doc = yaml.safe_load((WORKFLOWS / "backup.yml").read_text(encoding="utf-8"))
    runs = [
        s.get("run", "")
        for job in doc["jobs"].values()
        for s in job.get("steps") or []
        if "apt-get update" in (s.get("run") or "")
    ]

    assert runs, "backup.yml: لا خطوة apt — تحقّق قبل حذف هذا الحارس"
    assert all(HARDENING in r for r in runs)


def test_the_restore_drill_gets_its_apt_from_the_hardened_local_action():
    """الاستعادةُ الأسبوعيّةُ تُجدوَل بلا مراجعةٍ أيضاً. كان تثبيتُ PostgreSQL 18 بـapt في خطوتها؛ وصار في الإجراء
    المحلّيّ native-postgres (W-20261010-016) — فيلزم أن يبقى apt هناك محصَّناً وأن تستدعيه الاستعادة."""
    restore = yaml.safe_load((WORKFLOWS / "backup-restore-test.yml").read_text(encoding="utf-8"))
    steps = [s for job in restore["jobs"].values() for s in job.get("steps") or []]
    assert any(s.get("uses") == "./.github/actions/native-postgres" for s in steps)

    action = yaml.safe_load((ACTIONS / "native-postgres/action.yml").read_text(encoding="utf-8"))
    runs = [
        s.get("run", "")
        for s in action["runs"]["steps"]
        if "apt-get update" in (s.get("run") or "")
    ]
    assert runs, "native-postgres بلا apt — تحقّق قبل حذف هذا الحارس"
    assert all(HARDENING in r for r in runs)

"""حزمةُ الأدلّة على الطلبات (MAE-09، المرحلة 1): تصنيفٌ حتميٌّ من المسارات وتعليقٌ بلا نصٍّ من الوصف.

الأداةُ معلوماتيّةٌ لا بوّابة؛ وما يحرسه هذا الملفّ: التصنيفُ، وأنّ المجهولَ «عالية»، وأنّ سطرَ الاعتماد يُقرأ بتعبير بوّابة الدمج الآليّ
نفسِه، وأنّ التعليقَ لا ينسخ وصفَ الطلب، وأنّه يُحدَّث في مكانه، وأنّ المسارَ لا يُسقط الفحصَ ولا يُخفي فشلاً.
"""

import importlib.util
import json
import pathlib

import yaml

ROOT = pathlib.Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location("pr_evidence", ROOT / "scripts" / "pr_evidence.py")
pe = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(pe)

APPROVED = "اعتُمد من المالك على 8500 — 2026-10-02"


def _pr(paths, body="", **extra):
    return {
        "body": body,
        "files": [{"path": p, "additions": 1, "deletions": 0, **extra} for p in paths],
    }


def test_each_file_class():
    assert pe.classify("operations/migrations/0042_x.py") == "عالية"
    assert pe.classify("core/permissions.py") == "عالية"
    assert pe.classify("shschool/settings/production.py") == "عالية"
    assert pe.classify(".env.example") == "عالية"
    assert pe.classify("data/students.csv") == "عالية"
    assert pe.classify("templates/base/base.html") == "متوسّطة"
    assert pe.classify("operations/services/schedule.py") == "متوسّطة"
    assert pe.classify(".github/workflows/nightly.yml") == "منخفضة"
    assert pe.classify("scripts/ship.sh") == "منخفضة"
    assert pe.classify("tests/test_x.py") == "خفيفة"
    assert pe.classify("docs/governance/regression_guards.md") == "خفيفة"
    assert pe.classify("roadmap/migrations/0050_sync.py") == "خفيفة"  # بياناتٌ تملكها جلسةُ الخارطة


def test_an_unknown_file_is_high_not_low():
    assert pe.classify("weird/blob.xyz") == "عالية"


def test_the_overall_tier_is_the_highest_one():
    assert pe.overall(["docs/a.md", "tests/t.py"]) == "خفيفة"
    assert pe.overall(["docs/a.md", "core/views.py"]) == "متوسّطة"
    assert pe.overall(["docs/a.md", "core/views.py", "x/migrations/0001_a.py"]) == "عالية"
    assert pe.overall([]) == "خفيفة"


def test_the_approval_line_uses_the_auto_merge_gates_own_expression():
    assert pe.gate.APPROVAL.pattern  # مصدرٌ واحد: لا نسخةَ ثانيةً من التعبير
    assert "موجود ✔" in pe.render(_pr(["docs/a.md"], f"وصف\n\n{APPROVED}"))
    direct = "اعتُمد من المالك مباشرةً بلا معاينة 8500 — 2026-10-02"
    assert "موجود ✔" in pe.render(_pr(["docs/a.md"], direct))
    text = pe.render(_pr(["docs/a.md"], "اعتماد المالك 2026-10-02 على 8500"))
    assert "غيرُ موجود" in text and "موجود ✔" not in text


def test_the_comment_never_copies_the_pull_request_description():
    body = "نصٌّ من طرفٍ آخر: بريد a@b.com ورقم 12345678901 ودعوةٌ للتجاهل"
    text = pe.render(_pr(["core/views.py"], body))
    assert "a@b.com" not in text and "12345678901" not in text and "دعوةٌ" not in text


def test_migrations_and_blocked_paths_are_listed():
    text = pe.render(_pr(["operations/migrations/0042_x.py", "docs/a.md"]))
    assert "`operations/migrations/0042_x.py`" in text
    assert "يبقى الدمجُ يدويّاً" in text
    clean = pe.render(_pr(["docs/a.md"]))
    assert "**هجراتٌ:** لا" in clean and "الدمج الآليّ:** لا" in clean


def test_a_wholly_deleted_file_is_counted():
    data = {
        "body": "",
        "files": [
            {"path": "core/old.py", "additions": 0, "deletions": 40},
            {"path": "core/new.py", "additions": 5, "deletions": 2},
        ],
    }
    assert "1 حُذف كلُّه" in pe.render(data)


def test_the_comment_carries_the_marker_so_it_is_updated_not_repeated():
    assert pe.render(_pr(["docs/a.md"])).startswith(pe.MARKER)


def test_post_updates_the_existing_comment_in_place(monkeypatch):
    calls = []

    def fake(args, stdin=None):
        calls.append(args)

        class R:
            returncode = 0
            stdout = (
                json.dumps([7, f"قديم {pe.MARKER}"]) + "\n"
                if "comments" in args[-1] or "--paginate" in args
                else ""
            )
            stderr = ""

        return R()

    monkeypatch.setattr(pe, "sh", fake)
    assert pe.post("5", "o/r", "نصّ") is True
    assert any("PATCH" in c for c in calls) and not any("POST" in c for c in calls)


def test_post_creates_when_there_is_none_and_reports_a_refused_write(monkeypatch):
    def fake(args, stdin=None):
        class R:
            returncode = 1 if "POST" in args else 0
            stdout = ""
            stderr = ""

        return R()

    monkeypatch.setattr(pe, "sh", fake)
    assert pe.post("5", "o/r", "نصّ") is False  # نسخةٌ شقيقة: يُبلَّغ ولا يُرفع استثناء


def test_the_workflow_is_read_only_informational_and_does_not_hide_failure():
    wf = yaml.safe_load(
        (ROOT / ".github" / "workflows" / "pr-evidence.yml").read_text(encoding="utf-8")
    )
    triggers = wf.get("on") or wf.get(True)
    assert "pull_request" in triggers and "pull_request_target" not in triggers
    assert "edited" in triggers["pull_request"]["types"]  # يُعاد حين يُضاف سطرُ الاعتماد
    assert wf["permissions"] == {"contents": "read", "pull-requests": "write"}
    job = wf["jobs"]["evidence"]
    assert "continue-on-error" not in job and all(
        "continue-on-error" not in s for s in job["steps"]
    )
    run = " ".join(s.get("run", "") for s in job["steps"])
    assert "scripts/pr_evidence.py" in run and "|| true" not in run
    assert "${{" not in run  # لا حقنَ من سياق الحدث داخل الأمر: كلُّها عبر env

"""أفعالُ GitHub مثبَّتةٌ بتجزئةٍ كاملة لا بوسمٍ متحرّك (W-20261002-023، توصية 0105).

الوسمُ (`@v7`) قابلٌ للنقل: من ملك الوسمَ في مستودع الفعل يشغّل شيفرتَه في كلّ workflows ومعها GITHUB_TOKEN.
فكلُّ `uses:` خارجيٍّ يحمل SHA من 40 خانةً مع تعليقِ الوسم (يقرؤه Dependabot لتحديثه)، والمحليُّ `./` مستثنى.
"""

import pathlib
import re

import yaml

ROOT = pathlib.Path(__file__).resolve().parent.parent
USES = re.compile(r"^\s*(?:-\s*)?uses:\s*(?P<ref>[^\s#]+)(?P<tail>[^\n]*)$", re.M)
PINNED = re.compile(r"^[\w.-]+/[\w./-]+@[0-9a-f]{40}$")


def _files():
    return sorted(
        [*(ROOT / ".github/workflows").glob("*.yml"), *(ROOT / ".github/actions").rglob("*.yml")]
    )


def test_every_external_action_is_pinned_to_a_full_sha_with_a_version_comment():
    bad = []
    for f in _files():
        for m in USES.finditer(f.read_text(encoding="utf-8")):
            ref = m["ref"]
            if ref.startswith("./"):
                continue
            if not PINNED.match(ref) or not re.search(r"#\s*v?\d", m["tail"]):
                bad.append(f"{f.relative_to(ROOT)}: {ref}{m['tail']}")
    assert not bad, "أفعالٌ بوسمٍ متحرّكٍ أو بلا تعليق إصدار:\n" + "\n".join(bad)


def test_dependabot_updates_github_actions():
    cfg = yaml.safe_load((ROOT / ".github/dependabot.yml").read_text(encoding="utf-8"))
    eco = [u for u in cfg["updates"] if u["package-ecosystem"] == "github-actions"]
    assert eco and eco[0]["directory"] == "/"

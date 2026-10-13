"""عزلُ استحالة الحزمة المقنَّعة بتقليصٍ تصاعديّ (W-20261009-001): شعبةٌ ثم إضافةُ الشعب واحدةً واحدة،
ثمّ صفوفُ أوّل شعبةٍ تقلب النموذجَ إلى INFEASIBLE صفّاً صفّاً. معرّفاتٌ مقنَّعةٌ فقط.

التشغيل (من جذر الشجرة): PYTHONPATH=<shim>;. python scripts/v2_isolate_masked_infeasibility.py [perclass|base]
"""

import os
import sys

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "shschool.settings.testing")
sys.path.insert(0, ".")
import django  # noqa: E402

django.setup()
from operations.cpsat_adapter import DemandRow  # noqa: E402
from operations.scheduler_v2.model import ModelOptions, build_model  # noqa: E402
from tests.test_scheduler_v2_hard import (  # noqa: E402
    _NO_FAIRNESS,
    _derive_blocks,
    _fixture_inputs,
    solve,
)

MODE = sys.argv[1] if len(sys.argv) > 1 else "perclass"
#: الوضعُ القديم (كتلٌ بحسب المادّة لا المجموعة) يُظهر الخلل؛ الافتراضيُّ هو الصحيح.
PER_SUBJECT_BLOCKS = len(sys.argv) > 2 and sys.argv[2] == "per_subject"
FOUR = ("C-009", "C-012", "C-013", "C-017")
LABELS = {"G95", "G15", "G57", "G05"}


def group_blocks(inp, rows):
    """الكتل كما في `build_tasks`: مجموعةٌ متوازيةٌ مزدوجةٌ فقط إن كان كلُّ أعضائها مزدوجين، وإلّا حصصٌ مفردة."""
    members: dict[tuple, list] = {}
    for r in rows:
        if r.elec:
            members.setdefault((r.cls, r.elec), []).append(r)
    out = []
    for r in rows:
        if r.elec:
            ok = all(m.subj in inp.doubles for m in members[(r.cls, r.elec)])
        else:
            ok = r.subj in inp.doubles
        out.append(DemandRow(r.cls, r.subj, r.teacher, r.elec, r.n, r.joint, r.n // 2 if ok else 0))
    return out


def run(rows):
    inp = _fixture_inputs()
    inp.demand = rows if PER_SUBJECT_BLOCKS else group_blocks(inp, rows)
    if PER_SUBJECT_BLOCKS:
        _derive_blocks(inp, inp.doubles)
    st, sv = solve(build_model(inp, ModelOptions(**_NO_FAIRNESS)), workers=8, limit=60.0)
    return sv.StatusName(st)


base = _fixture_inputs().demand
rows = [
    DemandRow(
        r.cls,
        r.subj,
        r.teacher,
        ("G" + r.cls) if MODE == "perclass" and r.elec in LABELS else r.elec,
        r.n,
    )
    for r in base
]
classes = sorted({r.cls for r in rows})
kept: list[str] = []
flip = None
for c in classes:
    kept.append(c)
    s = run([r for r in rows if r.cls in kept])
    print("classes", len(kept), "+", c, s, flush=True)
    if s == "INFEASIBLE":
        flip = c
        break
if flip:
    mine = [r for r in rows if r.cls == flip]
    others = [r for r in rows if r.cls in kept and r.cls != flip]
    added: list = []
    for r in mine:
        added.append(r)
        s = run(others + added)
        print("row", r.subj, r.teacher, repr(r.elec), r.n, s, flush=True)
        if s == "INFEASIBLE":
            print("FIRST_FLIP", flip, r)
            break

"""نموذجُ CP-SAT مرجعاً لترميز قيود الجدول — لا محرّكاً للاستعمال كما هو.

نُقل من بيئةٍ معزولةٍ في 2026-10-01. قيمتُه في ترميز ما يصعب ترميزُه صحيحاً:
HC5 بالأوقات الفعليّة عبر النطاقات، وتضاربُ الشعبة مع المجموعات الاختياريّة،
وسعةُ المورد، وHC7، وسقفُ الحمل، والتفريغات.

وتحفّظان لا يُقرأ بدونهما (انظر README في المجلّد نفسِه):

1. دالّةُ هدفه تُصغّر الحركةَ عن جدولٍ قائم — وقد بطل ذلك بقرار المالك
   2026-10-01: الجدولُ يُستبدَل كاملاً فلا ميزانيّةَ حركةٍ تُقاس.
2. رايتا --capfirst و--maxlast قيدان **مقترحان** لا قائمان في المنصّة؛
   والقائمُ هو HC8 (سقفُ السابعة اثنتان) وحدَه. راجع المواصفة.

ويقرأ prod_data.json — وهو غيرُ مودَعٍ عمداً (أسماءٌ حقيقيّةٌ ومعرّفاتُ إنتاج).
"""

import json
import math
import sys
from collections import defaultdict

from ortools.sat.python import cp_model

D = json.load(open("prod_data.json", encoding="utf-8"))
bell, cb, T = D["bell"], D["class_band"], D["times"]
demand, doubles = D["demand"], set(D["doubles"])
ex_full = {tuple(r) for r in D["ex_full"]}
ex_per = {tuple(r) for r in D["ex_period"]}
prefs = {p["teacher_id"]: p for p in D["prefs"]}
res_cap = {r["id"]: r["capacity"] for r in D["resources"]}
res_subj = {k: set(v) for k, v in D["res_subjects"].items()}
res_name = {r["id"]: r["name"] for r in D["resources"]}
SN, TN, CN = D["subject_names"], D["teacher_names"], D["class_names"]
GAP, DEFAULT_MAX_DAILY = 10, 5
CAP_FIRST = int(next((a.split("=")[1] for a in sys.argv if a.startswith("--capfirst=")), 2))
MAX_LAST = int(next((a.split("=")[1] for a in sys.argv if a.startswith("--maxlast=")), 3))
LIMIT = float(next((a.split("=")[1] for a in sys.argv if a.startswith("--time=")), 600))
TOTAL = sum(r["n"] for r in demand)
ON = {a[7:] for a in sys.argv if a.startswith("--with=")}
ON = set(",".join(ON).split(",")) if ON else {"res", "hc7", "hc8", "maxd"}


def dtp(day):
    return "thursday" if day == 4 else "regular"


def bk(cls, day):
    return f"{cb[cls]}|{dtp(day)}"


def slots(cls, day):
    b = bell.get(bk(cls, day))
    return b["periods"] if b else []


m = cp_model.CpModel()
x = {}
for i, r in enumerate(demand):
    for day in range(5):
        for p in slots(r["cls"], day):
            if (r["teacher"], day) in ex_full or (r["teacher"], day, p) in ex_per:
                continue
            x[i, day, p] = m.NewBoolVar("")

for i, r in enumerate(demand):
    m.Add(sum(v for k, v in x.items() if k[0] == i) == r["n"])
    cap = max(1, math.ceil(r["n"] / 5))
    if r["subj"] in doubles:
        cap = max(cap, 2)
    for day in range(5):
        vs = [v for k, v in x.items() if k[0] == i and k[1] == day]
        if vs:
            m.Add(sum(vs) <= cap)
    if "hc7" in ON:
        byp = defaultdict(list)
        for k in x:
            if k[0] == i:
                byp[k[2]].append(x[k])
        for p, vs in byp.items():
            if len(vs) > 2:
                m.Add(sum(vs) <= 2)

by_cls, by_t = defaultdict(list), defaultdict(list)
for i, r in enumerate(demand):
    by_cls[r["cls"]].append(i)
    by_t[r["teacher"]].append(i)

for cls, idxs in by_cls.items():
    groups = sorted({demand[i]["elec"] for i in idxs})
    for day in range(5):
        for p in slots(cls, day):
            plain = [x[i, day, p] for i in idxs if demand[i]["elec"] == "" and (i, day, p) in x]
            if plain:
                m.Add(sum(plain) <= 1)
            for g in groups:
                if not g:
                    continue
                gv = [x[i, day, p] for i in idxs if demand[i]["elec"] == g and (i, day, p) in x]
                if gv:
                    m.Add(sum(gv) <= 1)
                    if plain:
                        m.Add(sum(plain) + sum(gv) <= 1)

if "res" in ON:
    for rid, cap in res_cap.items():
        subs = res_subj.get(rid, set())
        if not subs:
            continue
        for day in range(5):
            cells = defaultdict(list)
            for i, r in enumerate(demand):
                if r["subj"] not in subs:
                    continue
                for p in slots(r["cls"], day):
                    if (i, day, p) in x:
                        cells[p].append(x[i, day, p])
            for p, vs in cells.items():
                if len(vs) > cap:
                    m.Add(sum(vs) <= cap)

firsts, lasts = {}, {}
for t, idxs in by_t.items():
    pr = prefs.get(t) or {}
    maxd = pr.get("max_daily_periods") or DEFAULT_MAX_DAILY
    fv, lv = [], []
    for day in range(5):
        cells = defaultdict(list)
        for i in idxs:
            for p in slots(demand[i]["cls"], day):
                if (i, day, p) in x:
                    cells[p].append(x[i, day, p])
        if not cells:
            continue
        ps = sorted(cells)
        occ = {}
        for p, vs in cells.items():
            if len(vs) > 1:
                m.Add(sum(vs) <= 1)
            o = m.NewBoolVar("")
            m.AddMaxEquality(o, vs) if len(vs) > 1 else m.Add(o == vs[0])
            occ[p] = o
        if "maxd" in ON:
            m.Add(sum(occ.values()) <= maxd)
        fv.append(occ[ps[0]])
        lv.append(occ[ps[-1]])
        cand = [(i, p) for i in idxs for p in slots(demand[i]["cls"], day) if (i, day, p) in x]
        for a in range(len(cand)):
            ia, pa = cand[a]
            ka = bk(demand[ia]["cls"], day)
            for b in range(a + 1, len(cand)):
                ib, pb = cand[b]
                kb = bk(demand[ib]["cls"], day)
                ta, tb = T.get(ka, {}).get(str(pa)), T.get(kb, {}).get(str(pb))
                if not ta or not tb:
                    continue
                g = tb[0] - ta[1] if ta[1] <= tb[0] else ta[0] - tb[1]
                if g > GAP:
                    continue
                if (
                    demand[ia]["cls"] == demand[ib]["cls"]
                    and demand[ia]["subj"] == demand[ib]["subj"]
                    and demand[ia]["subj"] in doubles
                ):
                    continue
                m.Add(x[ia, day, pa] + x[ib, day, pb] <= 1)
    f = m.NewIntVar(0, 20, "")
    l = m.NewIntVar(0, 20, "")
    m.Add(f == sum(fv))
    m.Add(l == sum(lv))
    if "pattern" in ON:
        # النمطُ مباشرةً: إن بلغت الأولى ثلاثاً فالأخيرةُ واحدةٌ فأقلّ
        f3 = m.NewBoolVar("")
        m.Add(f >= 3).OnlyEnforceIf(f3)
        m.Add(f <= 2).OnlyEnforceIf(f3.Not())
        m.Add(l <= 1).OnlyEnforceIf(f3)
    else:
        m.Add(f <= CAP_FIRST)
    if "hc8" in ON:
        m.Add(l <= MAX_LAST)
    firsts[t], lasts[t] = f, l

idx_of = {(r["cls"], r["subj"], r["teacher"], r["elec"]): i for i, r in enumerate(demand)}
cur_cells = {}
kept = []
#: حزمةُ الاختبار المقنَّعةُ تُسقط `current` عمداً — وهو وضعُ V2 نفسِه: توليدٌ من
#: الصفر بلا جدولٍ سابق. فبلا جدولٍ لا ميزانيّةَ حركةٍ تُصغَّر، ويُحَلُّ للجدوى
#: وحدَها. ومع جدولٍ تعمل دالّةُ الهدف الأصليّة (وقد بطلت لجدول الإنتاج بقرار
#: المالك 2026-10-01، وتبقى صالحةً لأيّ مسألة إصلاحٍ أخرى).
for t, c, s, e, d, p in D.get("current", []):
    i = idx_of.get((c, s, t, e))
    if i is not None and (i, d, p) in x:
        kept.append(x[i, d, p])
        cur_cells.setdefault(i, []).append((d, p))
if kept:
    m.Minimize(TOTAL - sum(kept))

sv = cp_model.CpSolver()
sv.parameters.max_time_in_seconds = LIMIT
sv.parameters.num_search_workers = 8
st = sv.Solve(m)
print(f"قيودٌ مُنمذجةٌ زائدةً: {sorted(ON)} · سقفُ الأولى ≤ {CAP_FIRST} · سقفُ الأخيرة ≤ {MAX_LAST}")
print(f"الحالة: {sv.StatusName(st)} | الزمن: {round(sv.WallTime(),1)}ث")
if st not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
    print("لا حلّ — الهدفُ غيرُ قابلٍ للتحقيق بهذه القيود")
    raise SystemExit
if kept:
    moved = TOTAL - sum(1 for v in kept if sv.Value(v))
    print(f"أصغرُ حركةٍ: {moved} | حدٌّ أدنى مُثبَت: {int(sv.BestObjectiveBound())}")
else:
    print(f"توليدٌ من الصفر: {TOTAL} حصّةً وُضعت كلُّها (لا جدولَ سابقٍ فلا حركةَ تُقاس)")
print(
    f"أقصى أولى: {max(sv.Value(f) for f in firsts.values())} | أقصى أخيرة: {max(sv.Value(l) for l in lasts.values())}"
)
print(f"نمطُ المظلوم: {sum(1 for t in firsts if sv.Value(firsts[t])>=3 and sv.Value(lasts[t])>=2)}")

# فارقُ الحصص — بلا جدولٍ سابقٍ لا فارقَ يُحسب، فيُتخطّى كلُّه
if not cur_cells:
    raise SystemExit
new = defaultdict(list)
for (i, d, p), v in x.items():
    if sv.Value(v):
        new[i].append((d, p))
DAYN = ["الأحد", "الاثنين", "الثلاثاء", "الأربعاء", "الخميس"]
rows = []
for i, r in enumerate(demand):
    old = sorted(cur_cells.get(i, []))
    nw = sorted(new.get(i, []))
    gone = [c for c in old if c not in nw]
    came = [c for c in nw if c not in old]
    for a, b in zip(gone, came, strict=False):
        rows.append(
            {
                "teacher": TN.get(r["teacher"], "?"),
                "cls": CN.get(r["cls"], "?"),
                "subj": SN.get(r["subj"], "?"),
                "from": f"{DAYN[a[0]]} ح{a[1]}",
                "to": f"{DAYN[b[0]]} ح{b[1]}",
            }
        )
    for a in gone[len(came) :]:
        rows.append(
            {
                "teacher": TN.get(r["teacher"], "?"),
                "cls": CN.get(r["cls"], "?"),
                "subj": SN.get(r["subj"], "?"),
                "from": f"{DAYN[a[0]]} ح{a[1]}",
                "to": "—",
            }
        )
    for b in came[len(gone) :]:
        rows.append(
            {
                "teacher": TN.get(r["teacher"], "?"),
                "cls": CN.get(r["cls"], "?"),
                "subj": SN.get(r["subj"], "?"),
                "from": "—",
                "to": f"{DAYN[b[0]]} ح{b[1]}",
            }
        )
rows.sort(key=lambda z: (z["teacher"], z["cls"]))
json.dump(rows, open("diff_rows.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print(f"سطورُ الفارق: {len(rows)}")

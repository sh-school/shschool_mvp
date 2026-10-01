"""بناءُ حزمةِ اختبارٍ مُقنَّعةِ الهويّات من تصديرٍ حقيقيّ — D-93م (W-20261001-037).

المشكلة: حزمةُ مدخلات المولّد المصدَّرةُ من الإنتاج تحمل أسماءَ معلّمين حقيقيّةً
ومعرّفاتِ صفوفٍ فعليّة، فلا تُودَع في تاريخِ غيتٍ لا يُحذف (PDPPL — تقليلُ
البيانات). وبقاؤها خارجَ المستودع يترك V2 بلا حزمةِ اختبارٍ ثابتةٍ تصلح لـCI.

فيُبنى منها نظيرٌ **يحفظ البنيةَ الإحصائيّةَ ويُسقط الهويّة**:

    عددُ المعلّمين والشُّعب والموادّ · أحمالُ الطلب · الجرسُ والنطاقاتُ والأوقاتُ
    التفريغاتُ والتفضيلاتُ (قيمُها كما هي) · الموادُّ المزدوجةُ · سعاتُ الموارد

والمعرّفاتُ الجديدةُ **متسلسلةٌ صناعيّةٌ لا مشتقّةٌ من الأصل**: لا تجزئةَ ولا
تشفيرَ قابلاً للعكس — فمَن ملك قائمةَ المعرّفات الحقيقيّةَ لا يستطيع مطابقتَها
بجدولٍ معكوس. والخريطةُ لا تُحفظ ولا تُودَع.

ويُسقط حقلُ `current` كاملاً: جدولٌ قائمٌ بيانٌ تشغيليّ، وقد صار غيرَ مُلزِمٍ
بقرار المالك 2026-10-01 (الجدولُ يُستبدَل كاملاً).

    python anonymize_fixture.py <المصدر> <المخرَج>

والأسماءُ الباقيةُ ليست هويّاتٍ: أسماءُ الموادِّ منهجٌ معلَن، وأسماءُ الموارد
أوصافُ أماكنَ (ملعب، مختبر)، وأسماءُ الشُّعب صفٌّ وشعبةٌ لا شخص.
"""

from __future__ import annotations

import json
import os
import random
import sys
from collections import Counter, OrderedDict, defaultdict

#: الحقولُ التي تُسقط كاملةً — بياناتٌ تشغيليّةٌ لا مدخلاتُ توليد.
DROP = ("current",)

#: بذرةٌ من عشوائيّة النظام **ولا تُسجَّل** — فتسجيلُها يجعل الخريطةَ قابلةً
#: للإنتاج ثانيةً لمن ملك الأصل. والحزمةُ المودَعةُ هي الحجّة لا قابليّةُ
#: إعادة بنائها (D-96م).
RNG = random.Random(int.from_bytes(os.urandom(8), "big"))

#: هامشُ أمانٍ أسبوعيٌّ فوق السقف البنيويّ. فمعلّمٌ نصابُه يساوي سقفَه بالضبط
#: يلزمه بلوغُ الحدّ الأقصى في كلّ يومٍ من أيّامه، وتضاربُ شعبةٍ واحدٍ يُسقط
#: الجدولَ كلَّه. (قيس: نصابُ ١٦ مع يومٍ مُفرَّغٍ كاملاً = `INFEASIBLE`.)
WEEK_SLACK = 3

#: سقفُ نصابٍ مُولَّدٍ لمعلّم — دون أعلى نصابٍ حقيقيٍّ قيسَ (عشرون).
MAX_GEN_LOAD = 17


class Ids:
    """مُوزّعُ معرّفاتٍ صناعيّةٍ متسلسلة، ثابتٌ لكلّ قيمةٍ داخلَ التشغيل الواحد."""

    def __init__(self, prefix: str, width: int = 3) -> None:
        self.prefix, self.width, self.seen = prefix, width, OrderedDict()

    def __call__(self, real: str) -> str:
        if real not in self.seen:
            self.seen[real] = f"{self.prefix}-{len(self.seen) + 1:0{self.width}d}"
        return self.seen[real]

    def __len__(self) -> int:
        return len(self.seen)


def day_caps(src: dict) -> tuple[int, int]:
    """(أقصى حصصٍ غيرِ متلاصقةٍ في يومٍ عاديّ، وفي الخميس) — من الجرس لا بالحدس.

    الفجواتُ بين حصص التدريس صفرُ دقائق في هذه المدرسة، والفسحةُ والصلاةُ
    وحدَهما تفصلان؛ ومع `MAX_CONSECUTIVE = 1` (D-61م) لا يقف المعلّمُ حصّتين
    متلاصقتين. فالسقفُ اليوميُّ أقصى مجموعةٍ غيرِ متلاصقةٍ في الجرس — يُحسب
    بالأوقات الفعليّة عبر النطاقات لا بعدد الحصص.
    """
    reg, thu = [], []
    for key, band in src["bell"].items():
        #: جرسُ رمضان يومٌ آخرُ لا يدخل سقفَ الأسبوع العاديّ (وخمسُ حصصٍ فيه
        #: تخفض السقفَ كاذباً) — ولا شعبةَ تستعمله في بيانات 2026-10-01.
        if not key.endswith(("regular", "thursday")):
            continue
        times = src["times"].get(key, {})
        count, end = 0, None
        for period in band["periods"]:
            span = times.get(str(period))
            if not span:
                continue
            if end is None or span[0] - end > 10:
                count += 1
                end = span[1]
        (thu if key.endswith("thursday") else reg).append(count)
    return (min(reg) if reg else 4), (min(thu) if thu else 4)


def generate_teachers(src: dict) -> dict:
    """طبقةُ المعلّمين **مُولَّدةٌ** بقيدٍ بنيويّ — D-96م، بعد إخفاقَين مقيسين.

    الفرقُ الذي بُني عليه التصميم: **خطّةُ كلّ شعبةٍ (شعبة + مادّة + عددُ حصص)
    ليست بياناً شخصيّاً** — هي الخطّةُ الدراسيّة، تُترك حرفيّاً فتبقى الحزمةُ
    وفيّةً لصعوبة المسألة. **والشخصيُّ هو إسنادُ المعلّمين** وتفريغاتُهم
    وتفضيلاتُهم — فيُولَّد توليداً، فلا يبقى في الملفّ نصابُ أحدٍ ولا نمطُ
    تفريغه، ولا مطابقةَ ولا ندرةَ تُقاس.

    **وإخفاقان سبقا هذا التصميم، وقياسُهما هو تبريره:**

    1. *تشويشٌ بالإزاحة* (خلطُ معلّمين داخل المادّة، ثمّ إلزامُ k على قيم
       الأنصبة): فشل في **الخصوصيّة** — سبعةٌ وأربعون بالمئة حفظوا نصابَهم
       الحقيقيَّ بالضبط، وأقلُّ حاملي قيمةٍ واحدٌ في ثلاثٍ من خمس تشغيلات.
       والعلّةُ بنيويّة: النصابُ مجموعُ الصفوف، وأحجامُها في المادّة محدودةٌ،
       فكسرُ ندرةٍ يصنع أخرى.
    2. *توليدٌ بلا قيدٍ بنيويّ*: فشل في **الجدوى** — `INFEASIBLE` حتّى بلا أيّ
       سقفٍ اختياريّ. والسببُ معلّمٌ مُولَّدٌ نصابُه ستّةَ عشرَ ومعه يومٌ مُفرَّغٌ
       كاملاً: أربعٌ في كلّ يومٍ من أربعةٍ، على الحدّ البنيويّ بلا هامشٍ واحد.

    فصار التوليدُ مقيَّداً بسقف الجرس (`day_caps`) ناقصاً `WEEK_SLACK`، ولا
    يُمنح يومٌ مُفرَّغٌ كاملاً إلّا لمن يحتمله نصابُه بعد الهامش.
    """
    out = json.loads(json.dumps(src))
    dem = out["demand"]
    reg_cap, thu_cap = day_caps(src)
    ceiling = min(MAX_GEN_LOAD, reg_cap * 4 + thu_cap - WEEK_SLACK)

    #: التجميعُ بـ(مادّة، نطاق) لا بالمادّة وحدَها — وهذا هو الدرسُ الثالث:
    #: جرسُ النطاقات متداخلٌ بالساعة وفجواتُه صفر، فأكثرُ أزواج الحصص بين
    #: نطاقين متلاصقةٌ بالساعة، وHC5 يمنعها. فمعلّمٌ يخدم نطاقين يضيق يومُه إلى
    #: حصّتين أو ثلاث. وفي الواقع سبعةٌ وأربعون من اثنين وسبعين يخدمون نطاقاً
    #: واحداً — فتوليدٌ يخالف ذلك يُخرج حزمةً `INFEASIBLE` (قيس مرّتين).
    cb = src["class_band"]
    by_subj: dict = defaultdict(list)
    for i, row in enumerate(dem):
        by_subj[(row["subj"], cb[row["cls"]])].append(i)

    pool = [f"GEN-T-{k + 1:03d}" for k in range(len({r["teacher"] for r in dem}))]
    RNG.shuffle(pool)
    load: Counter = Counter()
    band_of: dict = {}
    taken: dict = defaultdict(set)

    #: ضمانتان صلبتان لا احتياطَ يتجاوزهما: **نطاقٌ واحدٌ لكلّ معلّم** (وإلّا
    #: ضاق يومُه بتلاصق الساعة بين النطاقات)، و**نصابٌ لا يبلغ السقفَ البنيويّ**
    #: (نصابُ واحدٍ وعشرين على سقفِ عشرين استحالةٌ حسابيّةٌ مضمونة — قيس).
    for _key, idxs in sorted(by_subj.items(), key=lambda z: -sum(dem[i]["n"] for i in z[1])):
        band = cb[dem[idxs[0]]["cls"]]
        for i in sorted(idxs, key=lambda j: -dem[j]["n"]):
            need = dem[i]["n"]
            #: والمجموعاتُ المتوازيةُ تلزمها معلّمون مختلفون: مادّتان في الخانة
            #: نفسِها لنصفَي الشعبة. وأربعُ شُعبٍ في هذه البيانات نصابُها سبعٌ
            #: وثلاثون وخاناتُها خمسٌ وثلاثون — فلا تُسع إلّا بالتوازي، ومعلّمٌ
            #: واحدٌ لمجموعتين يُسقط الحزمةَ كلَّها (`INFEASIBLE`، قيس).
            here = dem[i]["cls"], dem[i]["elec"]
            room = [
                t
                for t in pool
                if band_of.get(t, band) == band
                and load[t] + need <= ceiling
                and not any(c == here[0] and e and here[1] and e != here[1] for c, e in taken[t])
            ]
            if not room:
                raise SystemExit(
                    "تعذّر توليدُ طبقةِ معلّمين بهذا السقف — ارفع MAX_GEN_LOAD أو أنقص WEEK_SLACK"
                )
            #: الأخفُّ في نطاقه أوّلاً، ومن لم يُسند له نطاقٌ بعدُ يؤخَّر قليلاً
            #: حتى يُستنفد من هو في النطاق — فيقلّ عددُ من يخدم نطاقين.
            pick = min(room, key=lambda t: (t not in band_of, load[t], t))
            dem[i]["teacher"] = pick
            band_of[pick] = band
            load[pick] += need
            taken[pick].add(here)

    #: ولا معلّمَ بلا نصاب: يأخذ صفّاً من أثقلِ من يحتمل فقدَه في نطاقه.
    for teacher in pool:
        if load[teacher]:
            continue
        row = next(
            (
                i
                for donor in sorted(load, key=lambda z: -load[z])
                for i, r in enumerate(dem)
                if r["teacher"] == donor and load[donor] > r["n"]
            ),
            None,
        )
        if row is None:
            break
        previous = dem[row]["teacher"]
        dem[row]["teacher"] = teacher
        band_of[teacher] = cb[dem[row]["cls"]]
        load[teacher] += dem[row]["n"]
        load[previous] -= dem[row]["n"]

    #: اليومُ المُفرَّغُ كاملاً لمن يحتمله نصابُه على أربعة أيّامٍ بالهامش.
    four_day = reg_cap * 3 + thu_cap - WEEK_SLACK
    #: وشرطٌ ثانٍ لا يُغفَل: صفٌّ نصابُه خمسُ حصصٍ سقفُه حصّةٌ في اليوم، فيلزمه
    #: خمسةُ أيّامٍ مختلفة — فمن له صفٌّ كهذا لا يُمنح يوماً مُفرَّغاً أصلاً.
    #: (قيس: معلّمٌ نصابُه خمسٌ في صفٍّ واحدٍ ومعه يومٌ مُفرَّغ = `INFEASIBLE`.)
    biggest: Counter = Counter()
    for row in dem:
        biggest[row["teacher"]] = max(biggest[row["teacher"]], row["n"])
    eligible = [t for t in pool if load[t] <= four_day and biggest[t] <= 4]
    RNG.shuffle(eligible)
    out["ex_full"] = [[t, RNG.randrange(5)] for t in eligible[: len(src["ex_full"])]]

    #: وتفريغاتُ الحصص: أعدادُها كما هي، وأصحابُها ومواضعُها مُولَّدة، ولا
    #: تُعطى لمن نصابُه قريبٌ من سقفه.
    light = [t for t in pool if load[t] <= ceiling - 2] or pool
    owners = {t for t, *_ in src["ex_period"]}
    holders = RNG.sample(light, k=min(len(owners), len(light)))
    counts = sorted(
        (sum(1 for t, *_ in src["ex_period"] if t == o) for o in owners),
        reverse=True,
    )
    cells: set = set()
    out["ex_period"] = []
    for holder, want_n in zip(holders, counts, strict=False):
        made = 0
        while made < want_n:
            day, period = RNG.randrange(5), RNG.randrange(1, 8)
            if (holder, day, period) in cells:
                continue
            cells.add((holder, day, period))
            out["ex_period"].append([holder, day, period])
            made += 1

    #: والتفضيلُ يُسند لمن يحتمله: سقفٌ يوميٌّ شخصيٌّ منخفضٌ على معلّمٍ نصابُه
    #: عالٍ يُسقط الحزمةَ (`res,maxd` = `INFEASIBLE`، قيس). فيُشترط أن يبلغ
    #: نصابُه السقفَ الشخصيَّ في أيّامه بهامشٍ — ومن لا يحتمله لا يُسند له.
    free_days = {t: 5 - sum(1 for u, _ in out["ex_full"] if u == t) for t in pool}
    out["prefs"] = []
    used: set = set()
    for pref in src["prefs"]:
        personal = pref.get("max_daily_periods") or 5
        fits = [t for t in pool if t not in used and load[t] + 2 <= personal * free_days[t]]
        if not fits:
            continue
        owner = min(fits, key=lambda t: (load[t], t))
        used.add(owner)
        out["prefs"].append(
            {**{k: v for k, v in pref.items() if k != "teacher_id"}, "teacher_id": owner}
        )
    out["teacher_names"] = {t: t for t in pool}
    return out


def build(src: dict) -> dict:
    t_id, c_id, s_id, r_id, b_id = (
        Ids("T"),
        Ids("C"),
        Ids("S"),
        Ids("R", 2),
        Ids("B", 2),
    )

    #: الترتيبُ مقصود: تُسجَّل المعرّفاتُ من الطلب أوّلاً فيأخذ أثقلُ المعلّمين
    #: الرقمَ الأصغر، فيُقرأ المخرَجُ ويُراجَع بسهولةٍ بلا أثرٍ للهويّة.
    for row in src["demand"]:
        t_id(row["teacher"])
        c_id(row["cls"])
        s_id(row["subj"])

    out: dict = {}

    # الجرسُ والنطاقات — بنيةٌ زمنيّةٌ بحتة، ولا هويّةَ فيها إلّا اسمُ النطاق.
    out["bell"] = {f"{b_id(k.split('|')[0])}|{k.split('|')[1]}": v for k, v in src["bell"].items()}
    out["times"] = {
        f"{b_id(k.split('|')[0])}|{k.split('|')[1]}": v for k, v in src["times"].items()
    }
    out["class_band"] = {c_id(k): b_id(v) for k, v in src["class_band"].items()}

    out["demand"] = [
        {
            "cls": c_id(r["cls"]),
            "subj": s_id(r["subj"]),
            "teacher": t_id(r["teacher"]),
            "elec": r["elec"] and f"G{abs(hash(r['elec'])) % 97:02d}",
            "n": r["n"],
        }
        for r in src["demand"]
    ]
    out["doubles"] = sorted({s_id(s) for s in src["doubles"] if s in s_id.seen})
    out["ex_full"] = [[t_id(t), d] for t, d in src["ex_full"] if t in t_id.seen]
    out["ex_period"] = [[t_id(t), d, p] for t, d, p in src["ex_period"] if t in t_id.seen]

    out["prefs"] = [
        {**{k: v for k, v in p.items() if k != "teacher_id"}, "teacher_id": t_id(p["teacher_id"])}
        for p in src["prefs"]
        if p["teacher_id"] in t_id.seen
    ]

    #: أسماءُ الموادِّ منهجٌ معلَن فتبقى؛ وأسماءُ المعلّمين تُستبدل بترقيمٍ وصفيّ؛
    #: وأسماءُ الشُّعب تُبنى من الصفّ والشعبة بلا ربطٍ بالسجلّ الحقيقيّ.
    out["subject_names"] = {s_id(k): v for k, v in src["subject_names"].items() if k in s_id.seen}
    out["teacher_names"] = {v: f"معلّم {v.split('-')[1]}" for v in t_id.seen.values()}
    out["class_names"] = {v: f"شعبة {v.split('-')[1]}" for v in c_id.seen.values()}

    out["resources"] = [
        {"id": r_id(r["id"]), "name": r["name"], "capacity": r["capacity"]}
        for r in src["resources"]
    ]
    out["res_subjects"] = {
        r_id(k): sorted({s_id(s) for s in v if s in s_id.seen})
        for k, v in src["res_subjects"].items()
    }
    out["subjects"] = [
        {**{k: v for k, v in s.items() if k != "id"}, "id": s_id(s["id"])}
        for s in src["subjects"]
        if s["id"] in s_id.seen
    ]

    out["_fixture"] = {
        "origin": "خطّةٌ دراسيّةٌ حقيقيّةٌ مُقنَّعة + طبقةُ معلّمين مُولَّدة — D-93م/D-96م، W-20261001-037",
        "teachers": len(t_id),
        "classes": len(c_id),
        "subjects": len(s_id),
        "lessons": sum(r["n"] for r in src["demand"]),
        "dropped_fields": list(DROP),
        "note": (
            "خطّةُ كلّ شعبةٍ (شعبة + مادّة + عددُ حصص) مطابقةٌ للواقع حرفيّاً — وليست بياناً "
            "شخصيّاً. وطبقةُ المعلّمين (الإسنادُ والتفريغاتُ والتفضيلات) مُولَّدةٌ بقيد الجرس، "
            "فلا نصابَ شخصٍ ولا نمطَ تفريغه في الملفّ. والمعرّفاتُ صناعيّةٌ والخريطةُ والبذرةُ "
            "لم تُحفظا."
        ),
    }
    return out


def main() -> int:
    if len(sys.argv) != 3:
        sys.stderr.write(__doc__ or "")
        return 2
    src = json.load(open(sys.argv[1], encoding="utf-8"))
    out = build(generate_teachers(src))
    json.dump(out, open(sys.argv[2], "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    sys.stdout.write(
        f"{out['_fixture']['teachers']} معلّماً · {out['_fixture']['classes']} شعبةً · "
        f"{out['_fixture']['subjects']} مادّةً · {out['_fixture']['lessons']} حصّةً\n"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

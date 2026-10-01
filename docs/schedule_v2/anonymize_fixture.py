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

#: هامشٌ أسبوعيٌّ تحت السقف البنيويّ — صفرٌ بقرار مراجعة 0403: هامشٌ يُسهّل
#: المسألةَ بلا داعٍ، وأعلى نصابٍ حقيقيٍّ قيسَ عشرون وهو مجدولٌ فعلاً.
WEEK_SLACK = 0

#: سقفُ نصابٍ مُولَّدٍ لمعلّم — أعلى نصابٍ حقيقيٍّ قيس.
MAX_GEN_LOAD = 20

#: **مَدخلُ معايرةٍ لا توزيعٌ مرصود.** المرصودُ على الواقع (2026-10-01): خمسةٌ
#: وستّون بالمئة
#: نطاقاً واحداً، وستّةٌ وعشرون نطاقين، وثمانيةٌ ثلاثة. وهذا **ليس تجميلاً
#: إحصائيّاً**: خدمةُ نطاقين هي التفاعلُ الذي يضيق به يومُ المعلّم (جرسُ
#: النطاقات متداخلٌ بالساعة وفجواتُه صفرٌ، فأكثرُ أزواج الحصص بينها متلاصقةٌ
#: وHC5 يمنعها). وحزمةٌ كلُّ معلّميها في نطاقٍ واحدٍ **تحذف حالةَ القيد** فلا
#: تُثبت جدوى شيء — حكمُ 0403 على النسخة السابقة، وقد قُبل.
#: والأرقامُ أدناه **قبل الاستنزاف**: مؤهَّلٌ لنطاقين قد لا يقع له صفٌّ في
#: الثاني، فتنزل النسبةُ المحقَّقة. فعُيِّرت بالتجربة حتّى طابق **المحقَّقُ**
#: الواقعَ: 66/29/5 مقابل 65/26/8 مرصوداً (أربعُ تشغيلاتٍ، متوسّط).
BAND_MIX = ((1, 0.48), (2, 0.38), (3, 0.14))

#: وتوزيعُ تعدّد الموادّ كما قيس على الواقع: اثنان وثمانون بالمئة مادّةً
#: واحدةً، وسبعةَ عشرَ مادّتين، وواحدٌ ثلاثاً (المتوسّط 1.19). والترشيحُ
#: بالنطاق وحدَه يجعل كلَّ معلّمٍ مؤهَّلاً لكلّ مادّةٍ في نطاقه فتتراكم عليه
#: الموادُّ حتى 3.33 — **تخصّصٌ شبه معدومٍ لا وجودَ له في الواقع**. كشفته
#: مراجعةُ 0403 على الملفّ، وكان تقريري عنه خاطئاً بقياسٍ من نسخةٍ أقدم.
#: ومعايرتُها كذلك قبل الاستنزاف: المحقَّقُ 83/17 مقابل 82/17/1 مرصوداً.
SUBJ_MIX = ((1, 0.52), (2, 0.42), (3, 0.06))

#: وأنصبةُ متعدّدي النطاقات في الواقع 11..20 ووسيطُها 13، ومن يخدم ثلاثةً
#: أعلاه 16 — فيُسقَّف المُولَّدُ بمثله.
TRI_BAND_LOAD = 16

#: حجمُ مجموعة التنعيم: كلُّ هدفِ نصابٍ مُولَّدٍ هو **متوسّطُ ثلاثة أنصبةٍ
#: حقيقيّةٍ متجاورة**. فلا نصابُ شخصٍ بعينه في الملفّ، وكلُّ قيمةٍ يحملها ثلاثةٌ
#: على الأقلّ — وفي الوقت نفسِه يبقى **مدى** التوزيع كما هو (ثلاثٌ إلى عشرين).
#: وهذا يعالج ملاحظةَ 0403: حزمةٌ أنصبتُها متوازنةٌ في مدًى ضيّقٍ تُحَلُّ في
#: ثانيتين بدل مئةٍ وثمانٍ وأربعين — فقد تبدّد الضيقُ الذي يُراد اختبارُه.
SMOOTH_GROUP = 3


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


class Layer:
    """حالةُ توليدِ طبقةِ المعلّمين — تُمرَّر بين خطواتها بدل وسائطَ طويلة."""

    def __init__(self, src: dict, out: dict) -> None:
        self.out = out
        self.dem = out["demand"]
        self.cb = src["class_band"]
        reg_cap, thu_cap = day_caps(src)
        self.reg_cap, self.thu_cap = reg_cap, thu_cap
        self.ceiling = min(MAX_GEN_LOAD, reg_cap * 4 + thu_cap - WEEK_SLACK)
        self.pool = [f"GEN-T-{k + 1:03d}" for k in range(len({r["teacher"] for r in self.dem}))]
        RNG.shuffle(self.pool)
        self.load: Counter = Counter()
        self.taken: dict = defaultdict(set)
        self.mine_subj: dict = defaultdict(set)
        self.drift = 0
        self.serves: dict = {}
        self.target_of: dict = {}
        self.budget: dict = {}

    def cap_of(self, teacher: str) -> int:
        """سقفُ المعلّم: السقفُ البنيويُّ، وأخفضُ لمن يخدم ثلاثةَ نطاقات.

        والهدفُ (`target_of`) توجيهٌ في الترتيب لا سقفٌ صلب — سقفاً يُوقف
        التوليدَ حين يضيق معلّمو نطاقٍ (قيس: «تعذّر توليدُ طبقةِ معلّمين»).
        """
        return TRI_BAND_LOAD if len(self.serves[teacher]) >= 3 else self.ceiling

    def fits(self, teacher: str, need: int, cls: str, elec: str, band: str) -> bool:
        """أيقبل هذا المعلّمُ هذا الصفَّ؟ نطاقاً وسقفاً ومجموعةً متوازية.

        والمجموعاتُ المتوازيةُ تلزمها معلّمون مختلفون: مادّتان في الخانة نفسِها
        لنصفَي الشعبة. وأربعُ شُعبٍ في هذه البيانات نصابُها سبعٌ وثلاثون
        وخاناتُها خمسٌ وثلاثون — فلا تُسع إلّا بالتوازي، ومعلّمٌ واحدٌ لمجموعتين
        يُسقط الحزمةَ كلَّها (`INFEASIBLE`، قيس).
        """
        if band not in self.serves[teacher] or self.load[teacher] + need > self.cap_of(teacher):
            return False
        return not any(c == cls and e and elec and e != elec for c, e in self.taken[teacher])

    def give(self, index: int, teacher: str) -> None:
        """يُسند صفَّ الطلب إلى معلّمٍ ويُحدّث حالتَه."""
        row = self.dem[index]
        previous = row.get("teacher")
        if previous in self.load:
            self.load[previous] -= row["n"]
        row["teacher"] = teacher
        self.load[teacher] += row["n"]
        self.taken[teacher].add((row["cls"], row["elec"]))
        self.mine_subj[teacher].add(row["subj"])


def band_sets(state: Layer) -> dict:
    """مجموعةُ النطاقات لكلّ معلّم — والنطاقُ الأوّلُ بالتناسب مع حِمله.

    التجميعُ بالنطاق مقصود: جرسُ النطاقات متداخلٌ بالساعة وفجواتُه صفر،
    فأكثرُ أزواج الحصص بين نطاقين متلاصقةٌ وHC5 يمنعها — فمعلّمٌ يخدم نطاقين
    يضيق يومُه. وفي الواقع سبعةٌ وأربعون من اثنين وسبعين يخدمون نطاقاً واحداً.
    """
    need: Counter = Counter()
    for row in state.dem:
        need[state.cb[row["cls"]]] += row["n"]
    bands = sorted(need, key=lambda b: -need[b])
    total = sum(need.values())
    weighted = [b for b in bands for _ in range(max(1, round(20 * need[b] / total)))]
    counts = [max(1, round(len(state.pool) * share)) for _k, share in BAND_MIX]
    counts[0] = len(state.pool) - sum(counts[1:])
    serves: dict = {}
    cursor = 0
    for (how_many_bands, _share), how_many_teachers in zip(BAND_MIX, counts, strict=False):
        for _ in range(how_many_teachers):
            first = weighted[RNG.randrange(len(weighted))]
            extra = [b for b in bands if b != first]
            RNG.shuffle(extra)
            serves[state.pool[cursor]] = {first, *extra[: how_many_bands - 1]}
            cursor += 1
    return serves


def load_targets(src: dict, pool: list) -> dict:
    """أهدافُ النصاب: كلُّ هدفٍ متوسّطُ ثلاثةِ أنصبةٍ حقيقيّةٍ متجاورة.

    فيبقى **مدى** التوزيع كما هو ويذهب نصابُ الفرد — ولا قيمةَ في الملفّ هي
    نصابُ شخصٍ بعينه. والباقي يُوزَّع فيُحفظ المجموعُ تماماً.
    """
    real: Counter = Counter()
    for row in src["demand"]:
        real[row["teacher"]] += row["n"]
    ordered = sorted(real.values())
    targets: list = []
    for start in range(0, len(ordered), SMOOTH_GROUP):
        chunk = ordered[start : start + SMOOTH_GROUP]
        base, extra = divmod(sum(chunk), len(chunk))
        targets += [base + 1] * extra + [base] * (len(chunk) - extra)
    RNG.shuffle(targets)
    return dict(zip(pool, targets, strict=False))


def subject_budget(pool: list) -> dict:
    """ميزانيّةُ موادٍّ لكلّ معلّم — قيدُ تخصّصٍ لا أولويّة."""
    quota = [max(0, round(len(pool) * share)) for _k, share in SUBJ_MIX]
    quota[0] = len(pool) - sum(quota[1:])
    spread = [k for (k, _share), many in zip(SUBJ_MIX, quota, strict=False) for _ in range(many)]
    RNG.shuffle(spread)
    return dict(zip(pool, spread, strict=False))


def candidates(state: Layer, index: int, band: str) -> list:
    """من يقبل هذا الصفّ: المتخصّصُ أوّلاً، ثمّ صاحبُ ميزانيّة، ثمّ أيُّ أحد.

    والدرجةُ الثالثةُ تُحصى في `drift` وتُعلَن في `_fixture` فلا يُخفى تخصّصٌ
    أُضعف اضطراراً.
    """
    row = state.dem[index]
    args = (row["n"], row["cls"], row["elec"], band)
    room = [t for t in state.pool if row["subj"] in state.mine_subj[t] and state.fits(t, *args)]
    if room:
        return room
    room = [
        t for t in state.pool if len(state.mine_subj[t]) < state.budget[t] and state.fits(t, *args)
    ]
    if room:
        return room
    room = [t for t in state.pool if state.fits(t, *args)]
    if room:
        state.drift += 1
    return room


def assign_rows(state: Layer, by_subj: dict) -> None:
    """يُسند صفوفَ الطلب: المادّةُ الأثقلُ أوّلاً، والأبعدُ عن هدفه يأخذ.

    فتأخذ المادّةُ الثقيلةُ معلّميها وهم فارغون ولا تُحشر في البقيّة؛ ويتحقّق
    مدى الأنصبة بدل أن تتوازن في مدًى ضيّق.
    """
    order = sorted(by_subj.items(), key=lambda z: -sum(state.dem[i]["n"] for i in z[1]))
    for _key, idxs in order:
        band = state.cb[state.dem[idxs[0]]["cls"]]
        for index in sorted(idxs, key=lambda j: -state.dem[j]["n"]):
            room = candidates(state, index, band)
            if not room:
                raise SystemExit("تعذّر توليدُ طبقةِ معلّمين بهذه النسب — راجع BAND_MIX أو السقف")
            state.give(index, max(room, key=lambda t: (state.target_of[t] - state.load[t], t)))


def activate_bands(state: Layer) -> None:
    """يُفعّل خدمةَ النطاقات فعلاً لمن أُهّل لها ولم تقع له.

    معلّمٌ مؤهَّلٌ لنطاقين وقعت صفوفُه كلُّها في نطاقٍ واحدٍ **لا يُفعّل القيدَ
    الذي يُراد اختبارُه** — وحزمةٌ كذلك «تحذف حالةَ القيد» (حكمُ 0403). فيُنقل
    إليه صفٌّ من نطاقه الآخر، بشرط أن يبقى المانحُ في نطاقه (له فيه صفٌّ آخر):
    وشرطُ «أن يكون المانحُ متعدّدَ النطاقات أصلاً» عاطلٌ حين يبدأ الجميعُ
    بنطاقٍ واحد (قيس: التمريرةُ لم تُحرّك شيئاً والنتيجةُ مئةٌ بالمئة).
    """
    actual: dict = defaultdict(set)
    for row in state.dem:
        actual[row["teacher"]].add(state.cb[row["cls"]])
    for teacher in state.pool:
        for band in sorted(state.serves[teacher] - actual[teacher]):
            rows_in_band: Counter = Counter()
            for row in state.dem:
                rows_in_band[row["teacher"], state.cb[row["cls"]]] += 1
            moved = next(
                (
                    i
                    for i, row in enumerate(state.dem)
                    if state.cb[row["cls"]] == band
                    and row["teacher"] != teacher
                    and rows_in_band[row["teacher"], band] > 1
                    and (
                        row["subj"] in state.mine_subj[teacher]
                        or len(state.mine_subj[teacher]) < state.budget[teacher]
                    )
                    and state.fits(teacher, row["n"], row["cls"], row["elec"], band)
                ),
                None,
            )
            if moved is None:
                continue
            previous = state.dem[moved]["teacher"]
            state.give(moved, teacher)
            actual[teacher].add(band)
            actual[previous] = {state.cb[r["cls"]] for r in state.dem if r["teacher"] == previous}


def fill_empty(state: Layer) -> None:
    """لا معلّمَ بلا نصاب: يأخذ صفّاً من أثقلِ من يحتمل فقدَه في نطاقٍ يخدمه."""
    for teacher in state.pool:
        if state.load[teacher]:
            continue
        row = next(
            (
                i
                for donor in sorted(state.load, key=lambda z: -state.load[z])
                for i, r in enumerate(state.dem)
                if r["teacher"] == donor
                and state.load[donor] > r["n"]
                and state.cb[r["cls"]] in state.serves[teacher]
            ),
            None,
        )
        if row is not None:
            state.give(row, teacher)


def full_day_exemptions(state: Layer, src: dict) -> list:
    """اليومُ المُفرَّغُ كاملاً لمن يحتمله نصابُه على أربعة أيّامٍ بالهامش.

    وشرطٌ ثانٍ لا يُغفَل: صفٌّ نصابُه خمسُ حصصٍ سقفُه حصّةٌ في اليوم فيلزمه
    خمسةُ أيّامٍ مختلفة — فمن له صفٌّ كهذا لا يُمنح يوماً مُفرَّغاً أصلاً.
    (قيس: معلّمٌ نصابُه خمسٌ في صفٍّ واحدٍ ومعه يومٌ مُفرَّغ = `INFEASIBLE`.)
    """
    four_day = state.reg_cap * 3 + state.thu_cap - WEEK_SLACK
    biggest: Counter = Counter()
    for row in state.dem:
        biggest[row["teacher"]] = max(biggest[row["teacher"]], row["n"])
    eligible = [t for t in state.pool if state.load[t] <= four_day and biggest[t] <= 4]
    RNG.shuffle(eligible)
    return [[t, RNG.randrange(5)] for t in eligible[: len(src["ex_full"])]]


def period_exemptions(state: Layer, src: dict) -> list:
    """تفريغاتُ الحصص: أعدادُها كما هي، وأصحابُها ومواضعُها مُولَّدة.

    ولا تُعطى لمن نصابُه قريبٌ من سقفه.
    """
    light = [t for t in state.pool if state.load[t] <= state.ceiling - 2] or state.pool
    owners = {t for t, *_ in src["ex_period"]}
    holders = RNG.sample(light, k=min(len(owners), len(light)))
    counts = sorted((sum(1 for t, *_ in src["ex_period"] if t == o) for o in owners), reverse=True)
    cells: set = set()
    made: list = []
    for holder, want in zip(holders, counts, strict=False):
        while sum(1 for h, *_ in made if h == holder) < want:
            day, period = RNG.randrange(5), RNG.randrange(1, 8)
            if (holder, day, period) in cells:
                continue
            cells.add((holder, day, period))
            made.append([holder, day, period])
    return made


def preferences(state: Layer, src: dict, ex_full: list) -> list:
    """التفضيلُ يُسند لمن يحتمله: سقفٌ شخصيٌّ منخفضٌ على عاليِ النصاب يُسقط الحزمة.

    (`res,maxd` = `INFEASIBLE`، قيس.) فيُشترط أن يبلغ نصابُه السقفَ الشخصيَّ في
    أيّامه بهامشٍ — ومن لا يحتمله لا يُسند له.
    """
    free_days = {t: 5 - sum(1 for u, _ in ex_full if u == t) for t in state.pool}
    out: list = []
    used: set = set()
    for pref in src["prefs"]:
        personal = pref.get("max_daily_periods") or 5
        fits = [
            t for t in state.pool if t not in used and state.load[t] + 2 <= personal * free_days[t]
        ]
        if not fits:
            continue
        owner = min(fits, key=lambda t: (state.load[t], t))
        used.add(owner)
        out.append({**{k: v for k, v in pref.items() if k != "teacher_id"}, "teacher_id": owner})
    return out


def generate_teachers(src: dict) -> dict:
    """طبقةُ المعلّمين **مُولَّدةٌ** بقيدٍ بنيويّ — D-96م، بعد إخفاقاتٍ مقيسة.

    الفرقُ الذي بُني عليه التصميم: **خطّةُ كلّ شعبةٍ (شعبة + مادّة + عددُ حصص)
    ليست بياناً شخصيّاً** — هي الخطّةُ الدراسيّة، تُترك حرفيّاً فتبقى الحزمةُ
    وفيّةً لصعوبة المسألة. **والشخصيُّ هو إسنادُ المعلّمين** وتفريغاتُهم
    وتفضيلاتُهم — فيُولَّد توليداً، فلا يبقى في الملفّ نصابُ أحدٍ ولا نمطُ
    تفريغه، ولا مطابقةَ ولا ندرةَ تُقاس.

    **وثلاثةُ إخفاقاتٍ سبقت هذا التصميم، وقياسُها هو تبريره:**

    1. *تشويشٌ بالإزاحة* (خلطُ معلّمين داخل المادّة، ثمّ إلزامُ k على قيم
       الأنصبة): فشل في **الخصوصيّة** — سبعةٌ وأربعون بالمئة حفظوا نصابَهم
       الحقيقيَّ بالضبط. والعلّةُ بنيويّة: النصابُ مجموعُ الصفوف وأحجامُها في
       المادّة محدودةٌ، فكسرُ ندرةٍ يصنع أخرى.
    2. *توليدٌ بلا قيدٍ بنيويّ*: فشل في **الجدوى** — `INFEASIBLE` حتّى بلا أيّ
       سقفٍ اختياريّ (معلّمٌ نصابُه ستّةَ عشرَ ومعه يومٌ مُفرَّغٌ كاملاً).
    3. *مطابقةُ التوزيعات الهامشيّة وحدَها*: لا تضمن الجدوى — مرشَّحٌ
       `INFEASIBLE` ومرشَّحٌ بالنسب نفسِها `OPTIMAL`. فالإسنادُ نقطةٌ صالحةٌ في
       فضاءٍ ضيّق لا نمطٌ إحصائيّ، ويلزمه **تحقّقٌ بالحلّال** لا نسبٌ وحدَها.
    """
    out = json.loads(json.dumps(src))
    state = Layer(src, out)
    state.serves = band_sets(state)
    state.target_of = load_targets(src, state.pool)
    state.budget = subject_budget(state.pool)

    by_subj: dict = defaultdict(list)
    for i, row in enumerate(state.dem):
        by_subj[(row["subj"], state.cb[row["cls"]])].append(i)

    assign_rows(state, by_subj)
    activate_bands(state)
    fill_empty(state)

    out["ex_full"] = full_day_exemptions(state, src)
    out["ex_period"] = period_exemptions(state, src)
    out["prefs"] = preferences(state, src, out["ex_full"])
    out["teacher_names"] = {t: t for t in state.pool}
    OVERRUNS[0] = state.drift
    return out


#: يُحمل من آخر توليدٍ ليُعلَن في `_fixture`.
OVERRUNS = [0]


def renamed(src: dict, t_id: Ids, c_id: Ids, s_id: Ids) -> dict:
    """الأسماءُ: الموادُّ منهجٌ معلَن فتبقى، والمعلّمون والشُّعبُ ترقيمٌ وصفيّ."""
    return {
        "subject_names": {s_id(k): v for k, v in src["subject_names"].items() if k in s_id.seen},
        "teacher_names": {v: f"معلّم {v.split('-')[1]}" for v in t_id.seen.values()},
        "class_names": {v: f"شعبة {v.split('-')[1]}" for v in c_id.seen.values()},
    }


def resources_of(src: dict, r_id: Ids, s_id: Ids) -> dict:
    """المواردُ وموادُّها: أوصافُ أماكنَ وسعاتٌ — لا هويّاتَ أشخاصٍ فيها."""
    return {
        "resources": [
            {"id": r_id(r["id"]), "name": r["name"], "capacity": r["capacity"]}
            for r in src["resources"]
        ],
        "res_subjects": {
            r_id(k): sorted({s_id(s) for s in v if s in s_id.seen})
            for k, v in src["res_subjects"].items()
        },
        "subjects": [
            {**{k: v for k, v in x.items() if k != "id"}, "id": s_id(x["id"])}
            for x in src["subjects"]
            if x["id"] in s_id.seen
        ],
    }


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

    out.update(renamed(src, t_id, c_id, s_id))
    out.update(resources_of(src, r_id, s_id))

    out["_fixture"] = {
        "origin": "خطّةٌ دراسيّةٌ حقيقيّةٌ مُقنَّعة + طبقةُ معلّمين مُولَّدة — D-93م/D-96م، W-20261001-037",
        "teachers": len(t_id),
        "classes": len(c_id),
        "subjects": len(s_id),
        "lessons": sum(r["n"] for r in src["demand"]),
        "dropped_fields": list(DROP),
        "subject_budget_overruns": OVERRUNS[0],
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

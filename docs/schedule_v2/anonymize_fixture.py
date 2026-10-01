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
    taken: dict = defaultdict(set)

    #: حِملُ كلّ نطاقٍ أوّلاً، فيُوزَّع المعلّمون عليه بنسبته لا بالتساوي.
    band_need: Counter = Counter()
    for row in dem:
        band_need[cb[row["cls"]]] += row["n"]
    bands = sorted(band_need, key=lambda b: -band_need[b])
    total_need = sum(band_need.values())

    #: مجموعاتُ النطاقات: من يخدم نطاقاً، ومن يخدم اثنين، ومن ثلاثة — بالنسب
    #: المقيسة. والنطاقُ الأوّلُ لكلّ معلّمٍ يُسحب بالتناسب مع حِمل النطاقات،
    #: والإضافيُّ عشوائيٌّ من البقيّة.
    serves: dict = {}
    counts = [max(1, round(len(pool) * share)) for _k, share in BAND_MIX]
    counts[0] = len(pool) - sum(counts[1:])
    cursor = 0
    weighted = [b for b in bands for _ in range(max(1, round(20 * band_need[b] / total_need)))]
    for (k, _share), how_many in zip(BAND_MIX, counts, strict=False):
        for _ in range(how_many):
            first = weighted[RNG.randrange(len(weighted))]
            extra = [b for b in bands if b != first]
            RNG.shuffle(extra)
            serves[pool[cursor]] = {first, *extra[: k - 1]}
            cursor += 1

    #: أهدافُ النصاب: الأنصبةُ الحقيقيّةُ مُرتَّبةً، ثمّ كلُّ ثلاثةٍ متجاورةٍ
    #: تُستبدل بثلاثِ نسخٍ من متوسّطها (والباقي يُوزَّع فيحفظ المجموع تماماً).
    #: فيبقى المدى ويذهب نصابُ الفرد.
    real_loads = Counter()
    for row in src["demand"]:
        real_loads[row["teacher"]] += row["n"]
    ordered = sorted(real_loads.values())
    targets: list = []
    for start in range(0, len(ordered), SMOOTH_GROUP):
        chunk = ordered[start : start + SMOOTH_GROUP]
        base, extra = divmod(sum(chunk), len(chunk))
        targets += [base + 1] * extra + [base] * (len(chunk) - extra)
    RNG.shuffle(targets)

    #: ميزانيّةُ موادٍّ لكلّ معلّمٍ بالنسب المقيسة — قيدُ تخصّصٍ لا أولويّة.
    quota = [max(0, round(len(pool) * share)) for _k, share in SUBJ_MIX]
    quota[0] = len(pool) - sum(quota[1:])
    spread = [k for (k, _share), many in zip(SUBJ_MIX, quota, strict=False) for _ in range(many)]
    RNG.shuffle(spread)
    budget = dict(zip(pool, spread, strict=False))
    mine_subj: dict = defaultdict(set)
    drift = [0]

    def ceiling_for(teacher: str) -> int:
        #: الهدفُ توجيهٌ في الترتيب لا سقفٌ صلب: سقفاً يُوقف التوليدَ حين يضيق
        #: معلّمو نطاقٍ (قيس: «تعذّر توليدُ طبقةِ معلّمين»). والسقفُ البنيويُّ
        #: وحدَه يمنع، والهدفُ يجذب.
        return TRI_BAND_LOAD if len(serves[teacher]) >= 3 else ceiling

    target_of = dict(zip(pool, targets, strict=False))

    #: المادّةُ الأثقلُ أوّلاً: تأخذ معلّميها وهم فارغون فلا تُحشر في البقيّة.
    for _key, idxs in sorted(by_subj.items(), key=lambda z: -sum(dem[i]["n"] for i in z[1])):
        band = cb[dem[idxs[0]]["cls"]]
        for i in sorted(idxs, key=lambda j: -dem[j]["n"]):
            need = dem[i]["n"]
            here = dem[i]["cls"], dem[i]["elec"]
            #: والمجموعاتُ المتوازيةُ تلزمها معلّمون مختلفون: مادّتان في الخانة
            #: نفسِها لنصفَي الشعبة. وأربعُ شُعبٍ في هذه البيانات نصابُها سبعٌ
            #: وثلاثون وخاناتُها خمسٌ وثلاثون — فلا تُسع إلّا بالتوازي، ومعلّمٌ
            #: واحدٌ لمجموعتين يُسقط الحزمةَ كلَّها (`INFEASIBLE`، قيس).
            subject = dem[i]["subj"]

            def fits(t, need=need, here=here, band=band):
                return (
                    band in serves[t]
                    and load[t] + need <= ceiling_for(t)
                    and not any(
                        c == here[0] and e and here[1] and e != here[1] for c, e in taken[t]
                    )
                )

            #: المتخصّصُ في المادّة أوّلاً، ثمّ من بقيت له ميزانيّةُ مادّةٍ
            #: جديدة، ثمّ — عند الضيق وحدَه — أيُّ معلّمٍ في النطاق، ويُحصى
            #: الانحرافُ ويُعلَن في `_fixture` فلا يُخفى تخصّصٌ أُضعف اضطراراً.
            room = [t for t in pool if subject in mine_subj[t] and fits(t)]
            if not room:
                room = [t for t in pool if len(mine_subj[t]) < budget[t] and fits(t)]
            if not room:
                room = [t for t in pool if fits(t)]
                drift[0] += 1
            if not room:
                raise SystemExit("تعذّر توليدُ طبقةِ معلّمين بهذه النسب — راجع BAND_MIX أو السقف")
            #: الأبعدُ عن هدفه أوّلاً — فتتحقّق الأهدافُ بدل أن تتوازن
            #: الأنصبةُ في مدًى ضيّق.
            pick = max(room, key=lambda t: (target_of[t] - load[t], t))
            dem[i]["teacher"] = pick
            load[pick] += need
            taken[pick].add(here)
            mine_subj[pick].add(subject)

    #: تمريرةٌ تُفعّل خدمةَ النطاقات فعلاً: معلّمٌ مؤهَّلٌ لنطاقين وقد وقعت
    #: صفوفُه كلُّها في نطاقٍ واحدٍ لا يُفعّل القيدَ الذي يُراد اختبارُه — وحزمةٌ
    #: كذلك «تحذف حالةَ القيد» (حكمُ 0403). فيُنقل إليه صفٌّ من نطاقه الآخر.
    actual: dict = defaultdict(set)
    for row in dem:
        actual[row["teacher"]].add(cb[row["cls"]])
    for teacher in pool:
        for band in sorted(serves[teacher] - actual[teacher]):
            #: والمانحُ يُشترط أن يبقى في نطاقه بعد المنح (له فيه صفٌّ آخر) —
            #: لا أن يكون متعدّدَ النطاقات أصلاً، فذاك شرطٌ عاطلٌ حين يبدأ
            #: الجميعُ بنطاقٍ واحد (قيس: التمريرةُ لم تُحرّك شيئاً والنتيجةُ
            #: مئةٌ بالمئة نطاقاً واحداً). والمادّةُ تُحترم كذلك: التخصّصُ قيدٌ.
            rows_in_band: Counter = Counter()
            for r in dem:
                rows_in_band[r["teacher"], cb[r["cls"]]] += 1
            moved = next(
                (
                    i
                    for i, r in enumerate(dem)
                    if cb[r["cls"]] == band
                    and r["teacher"] != teacher
                    and rows_in_band[r["teacher"], band] > 1
                    and (
                        r["subj"] in mine_subj[teacher] or len(mine_subj[teacher]) < budget[teacher]
                    )
                    and load[teacher] + r["n"] <= ceiling_for(teacher)
                    and not any(
                        c == r["cls"] and e and r["elec"] and e != r["elec"]
                        for c, e in taken[teacher]
                    )
                ),
                None,
            )
            if moved is None:
                continue
            previous = dem[moved]["teacher"]
            dem[moved]["teacher"] = teacher
            load[previous] -= dem[moved]["n"]
            load[teacher] += dem[moved]["n"]
            taken[teacher].add((dem[moved]["cls"], dem[moved]["elec"]))
            actual[teacher].add(band)
            mine_subj[teacher].add(dem[moved]["subj"])
            actual[previous] = {cb[r["cls"]] for r in dem if r["teacher"] == previous}

    #: ولا معلّمَ بلا نصاب: يأخذ صفّاً من أثقلِ من يحتمل فقدَه في نطاقٍ يخدمه.
    for teacher in pool:
        if load[teacher]:
            continue
        row = next(
            (
                i
                for donor in sorted(load, key=lambda z: -load[z])
                for i, r in enumerate(dem)
                if r["teacher"] == donor
                and load[donor] > r["n"]
                and cb[r["cls"]] in serves[teacher]
            ),
            None,
        )
        if row is None:
            continue
        previous = dem[row]["teacher"]
        dem[row]["teacher"] = teacher
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
    OVERRUNS[0] = drift[0]
    return out


#: يُحمل من آخر توليدٍ ليُعلَن في `_fixture`.
OVERRUNS = [0]


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

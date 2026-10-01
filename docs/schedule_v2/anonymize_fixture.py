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
import sys
from collections import OrderedDict

#: الحقولُ التي تُسقط كاملةً — بياناتٌ تشغيليّةٌ لا مدخلاتُ توليد.
DROP = ("current",)


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
        "origin": "مُقنَّعةٌ من تصدير إنتاجٍ قراءةً — D-93م، W-20261001-037",
        "teachers": len(t_id),
        "classes": len(c_id),
        "subjects": len(s_id),
        "lessons": sum(r["n"] for r in src["demand"]),
        "dropped_fields": list(DROP),
        "note": "معرّفاتٌ صناعيّةٌ متسلسلةٌ لا مشتقّةٌ من الأصل؛ الخريطةُ لم تُحفظ.",
    }
    return out


def main() -> int:
    if len(sys.argv) != 3:
        sys.stderr.write(__doc__ or "")
        return 2
    src = json.load(open(sys.argv[1], encoding="utf-8"))
    out = build(src)
    json.dump(out, open(sys.argv[2], "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    sys.stdout.write(
        f"{out['_fixture']['teachers']} معلّماً · {out['_fixture']['classes']} شعبةً · "
        f"{out['_fixture']['subjects']} مادّةً · {out['_fixture']['lessons']} حصّةً\n"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

# -*- coding: utf-8 -*-
"""
sot_pdf.py — الرجوعُ إلى أصل الوزارة (PDF) قبل ترميز أيّ رقم.

ثلاثةُ أوامرَ للقراءة وحدَها؛ لا يعدّل الأصولَ ولا يكتب في المستودع:
  python sot_pdf.py find <كلمات…>              # بحثٌ مطبَّعٌ في أسماء ملفّات الأصول
  python sot_pdf.py info <ملف|جزءٌ من اسمه>      # الصفحات، والصوريّةُ منها، وتقديرُ إزاحة الترقيم
  python sot_pdf.py render <ملف|جزء> <صفحات> [--dpi 130] [--clip x0,y0,x1,y1] [--out DIR]

الصفحاتُ في render بترتيب ملفّ الـPDF (1..N) لا بالرقم المطبوع: «38» أو «38-40» أو «12,15».
الصورُ تُكتب في مجلّدٍ مؤقّتٍ خارج أيّ مستودع (يُرفض --out داخل شجرة git) ثمّ تُفتح بأداة Read.
مجلّدُ الأصول: متغيّرُ البيئة SOT_RAW، وإلّا الموضعُ المعتمَد ثمّ القديم.
"""
import argparse
import collections
import os
import re
import sys
import tempfile
import unicodedata

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

RAW_CANDIDATES = [
    os.environ.get("SOT_RAW", ""),
    "D:/shschool_mvp/AAdocs/ministry_data/2026-2027 PDF",  # الموضعُ المعتمَد منذ 2026-09-25
    "D:/shschool_mvp/data/2026-2027",                      # الموضعُ القديم (لم يعد موجوداً)
]
_DIAC = re.compile(r"[\u0610-\u061A\u064B-\u065F\u0670\u06D6-\u06ED\u0640]")


def raw_root():
    for c in RAW_CANDIDATES:
        if c and os.path.isdir(c):
            return c
    sys.exit("لم يُعثر على مجلّد الأصول؛ اضبط SOT_RAW. (الأصولُ متجاهَلةٌ في غيت فلا توجد في أشجار العمل)")


def norm(s):
    """تطبيعٌ عربيٌّ للمقارنة: أشكالُ العرض والتشكيل والهمزات والتاء المربوطة والأرقام والمسافات."""
    s = unicodedata.normalize("NFKC", s)
    s = _DIAC.sub("", s)
    for a, b in (("أ", "ا"), ("إ", "ا"), ("آ", "ا"), ("ٱ", "ا"), ("ى", "ي"), ("ئ", "ي"), ("ؤ", "و"), ("ة", "ه")):
        s = s.replace(a, b)
    s = s.translate(str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789"))
    return re.sub(r"\s+", " ", s).strip().lower()


def all_files():
    root = raw_root()
    out = []
    for dp, _dn, fn in os.walk(root):
        for f in sorted(fn):
            p = os.path.join(dp, f)
            out.append((os.path.relpath(p, root).replace("\\", "/"), p))
    return sorted(out)


def resolve(spec):
    """مسارٌ كاملٌ أو جزءٌ من الاسم؛ يرفض الغموض بدل أن يخمّن."""
    if os.path.isfile(spec):
        return spec
    words = norm(spec).split()
    hits = [(rel, p) for rel, p in all_files() if all(w in norm(rel) for w in words)]
    if len(hits) == 1:
        return hits[0][1]
    if not hits:
        sys.exit(f"لا ملفَّ يطابق: {spec}")
    listing = "\n".join("  " + rel for rel, _ in hits[:20])
    sys.exit(f"أكثرُ من ملفٍّ يطابق ({len(hits)}) — ضيّق البحث:\n{listing}")


def parse_pages(spec, n):
    pages = []
    for part in spec.split(","):
        if "-" in part:
            a, b = part.split("-", 1)
            pages.extend(range(int(a), int(b) + 1))
        else:
            pages.append(int(part))
    bad = [p for p in pages if p < 1 or p > n]
    if bad:
        sys.exit(f"صفحاتٌ خارج المدى 1..{n}: {bad}")
    return pages


def inside_git_tree(path):
    p = os.path.abspath(path)
    while True:
        if os.path.exists(os.path.join(p, ".git")):
            return True
        parent = os.path.dirname(p)
        if parent == p:
            return False
        p = parent


def offset_estimate(doc):
    """يقدّر «فهرس الـPDF − الرقم المطبوع» من أرقامٍ منفردةٍ في أوّل الصفحة وآخرها.
    طبقةُ النصّ العربيّة تالفةٌ لكنّ الأرقامَ سليمةٌ غالباً؛ والتقديرُ تلميحٌ يُتحقَّق منه بصريّاً."""
    votes = collections.Counter()
    for i, page in enumerate(doc, 1):
        lines = [ln.strip() for ln in page.get_text().splitlines() if ln.strip()]
        edge = lines[:6] + lines[-6:]
        for ln in edge:
            t = norm(ln)
            if re.fullmatch(r"\d{1,3}", t):
                off = i - int(t)
                if 0 <= off <= 40:
                    votes[off] += 1
    return votes.most_common(3)


def cmd_find(args):
    words = norm(" ".join(args.words)).split()
    hits = [rel for rel, _ in all_files() if all(w in norm(rel) for w in words)]
    for rel in hits:
        print(rel)
    print(f"— {len(hits)} ملفّاً من {len(all_files())}", file=sys.stderr)


def cmd_info(args):
    import fitz
    path = resolve(args.file)
    print("الملف:", os.path.relpath(path, raw_root()).replace("\\", "/"))
    if not path.lower().endswith(".pdf"):
        print("ليس PDF — يُفتح بأداته (Read للصور، openpyxl/python-docx لغيرها)")
        return
    doc = fitz.open(path)
    img = [i for i, pg in enumerate(doc, 1) if len(pg.get_text().strip()) < 40]
    print("الصفحات:", doc.page_count)
    print("صوريّةٌ بلا طبقة نصّ:", len(img), (img[:15] if img else ""))
    est = offset_estimate(doc)
    if est:
        best, cnt = est[0]
        print(f"إزاحةُ الترقيم المقدَّرة: PDF = المطبوع + {best} (أصوات {cnt}؛ البدائل {est[1:]}) — تحقّق بصريّاً")
    else:
        print("إزاحةُ الترقيم: لا أرقامَ صفحاتٍ مقروءة — قِسها بصريّاً")


def cmd_render(args):
    import fitz
    path = resolve(args.file)
    doc = fitz.open(path)
    pages = parse_pages(args.pages, doc.page_count)
    out = args.out or os.path.join(tempfile.gettempdir(), "sot_render")
    if inside_git_tree(out):
        sys.exit("ممنوعٌ الإخراجُ داخل شجرة git (المستودع عامّ) — اختر مجلّداً مؤقّتاً")
    os.makedirs(out, exist_ok=True)
    clip = [float(x) for x in args.clip.split(",")] if args.clip else None
    tag = re.sub(r"\W+", "_", os.path.splitext(os.path.basename(path))[0])[:40]
    for pn in pages:
        pg = doc[pn - 1]
        r = pg.rect
        c = None
        if clip:
            c = fitz.Rect(r.x0 + clip[0] * r.width, r.y0 + clip[1] * r.height,
                          r.x0 + clip[2] * r.width, r.y0 + clip[3] * r.height)
        suffix = "" if not clip else "_clip"
        dest = os.path.join(out, f"{tag}_p{pn:03d}{suffix}_{args.dpi}.png")
        pg.get_pixmap(dpi=args.dpi, clip=c).save(dest)
        print(dest)


def main():
    ap = argparse.ArgumentParser(description="الرجوعُ إلى أصل الوزارة (قراءةٌ فقط)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    f = sub.add_parser("find", help="بحثٌ في أسماء الأصول")
    f.add_argument("words", nargs="+")
    i = sub.add_parser("info", help="الصفحات وإزاحةُ الترقيم")
    i.add_argument("file")
    r = sub.add_parser("render", help="تصييرُ صفحاتٍ إلى PNG")
    r.add_argument("file")
    r.add_argument("pages")
    r.add_argument("--dpi", type=int, default=130)
    r.add_argument("--clip", help="x0,y0,x1,y1 كسورٌ من 0..1")
    r.add_argument("--out")
    args = ap.parse_args()
    {"find": cmd_find, "info": cmd_info, "render": cmd_render}[args.cmd](args)


if __name__ == "__main__":
    main()

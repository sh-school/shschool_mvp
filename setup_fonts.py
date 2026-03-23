"""
setup_fonts.py — تجهيز خطوط عربية لـ WeasyPrint / xhtml2pdf
شغّل مرة واحدة:  python setup_fonts.py
"""

import logging
import os
import shutil
import sys
import urllib.request

logger = logging.getLogger(__name__)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
FONTS_DIR = os.path.join(BASE_DIR, "static", "fonts")
os.makedirs(FONTS_DIR, exist_ok=True)

# ── خطوط Windows الموجودة أصلاً تدعم العربية ──
WINDOWS_FONTS = {
    "Amiri-Regular.ttf": [
        r"C:\Windows\Fonts\tahoma.ttf",
        r"C:\Windows\Fonts\arial.ttf",
    ],
    "Amiri-Bold.ttf": [
        r"C:\Windows\Fonts\tahomabd.ttf",
        r"C:\Windows\Fonts\arialbd.ttf",
    ],
}

# ── روابط تحميل مباشرة (jsDelivr CDN — موثوق) ──
CDN_URLS = {
    "Amiri-Regular.ttf": [
        "https://cdn.jsdelivr.net/npm/@fontsource/amiri@5.0.8/files/amiri-arabic-400-normal.woff2",
        "https://fonts.gstatic.com/s/amiri/v27/J7aRnpd8CGxBHqUpvrIw74NL.ttf",
    ],
    "Amiri-Bold.ttf": [
        "https://fonts.gstatic.com/s/amiri/v27/J7acnpd8CGxBHpUutLMA7w.ttf",
    ],
}


def try_windows_copy():
    """انسخ من خطوط Windows إذا كانت موجودة"""
    copied = 0
    for dest_name, sources in WINDOWS_FONTS.items():
        dest = os.path.join(FONTS_DIR, dest_name)
        if os.path.exists(dest):
            print(f"   ✅ موجود: {dest_name}")
            copied += 1
            continue
        for src in sources:
            if os.path.exists(src):
                shutil.copy2(src, dest)
                print(f"   ✅ نُسخ من Windows: {os.path.basename(src)} → {dest_name}")
                copied += 1
                break
    return copied


def try_download():
    """حاول التحميل من CDN"""
    opener = urllib.request.build_opener()
    opener.addheaders = [("User-Agent", "Mozilla/5.0")]
    urllib.request.install_opener(opener)

    downloaded = 0
    for dest_name, urls in CDN_URLS.items():
        dest = os.path.join(FONTS_DIR, dest_name)
        if os.path.exists(dest) and os.path.getsize(dest) > 10000:
            downloaded += 1
            continue
        for url in urls:
            try:
                print(f"   ⏳ {dest_name} ...", end=" ", flush=True)
                urllib.request.urlretrieve(url, dest)
                if os.path.getsize(dest) > 1000:
                    print(f"✅ ({os.path.getsize(dest)//1024} KB)")
                    downloaded += 1
                    break
                else:
                    os.remove(dest)
            except Exception:
                logger.exception("فشل تحميل الخط %s من %s", dest_name, url)
                pass
    return downloaded


print("=" * 55)
print("  تجهيز خطوط عربية لـ SchoolOS PDF")
print("=" * 55)

# المحاولة 1: خطوط Windows
print("\n📂 خطوات 1/2 — البحث عن خطوط Windows...")
win_count = try_windows_copy()

# المحاولة 2: تحميل من الإنترنت
if win_count < 2:
    print("\n🌐 خطوة 2/2 — محاولة التحميل من الإنترنت...")
    dl_count = try_download()
else:
    dl_count = 0

total = len(
    [
        f
        for f in ["Amiri-Regular.ttf", "Amiri-Bold.ttf"]
        if os.path.exists(os.path.join(FONTS_DIR, f))
    ]
)

print(f"\n{'='*55}")
if total >= 1:
    print(f"✅ جاهز! {total}/2 خط في: static/fonts/")
    print("\nشغّل الآن:")
    print("   python manage.py collectstatic --noinput")
else:
    print("⚠️  لم يُوجد خط تلقائياً.")
    print("\nالحل اليدوي السريع:")
    print("1. افتح المتصفح وحمّل:")
    print("   https://fonts.google.com/specimen/Amiri")
    print("   أو: https://github.com/aliftype/amiri/releases")
    print(f"2. ضع الملفات في: {FONTS_DIR}")
    print("   - Amiri-Regular.ttf")
    print("   - Amiri-Bold.ttf")
    print("\nبديل مؤقت (خط Windows مباشر):")
    print("   python setup_fonts.py --use-tahoma")

    # إذا استُدعي مع --use-tahoma
    if "--use-tahoma" in sys.argv:
        print("\nجاري استخدام Tahoma (خط Windows مدمج)...")
        for dest_name, sources in WINDOWS_FONTS.items():
            dest = os.path.join(FONTS_DIR, dest_name)
            for src in sources:
                if os.path.exists(src):
                    shutil.copy2(src, dest)
                    print(f"✅ {os.path.basename(src)} → {dest_name}")
                    break

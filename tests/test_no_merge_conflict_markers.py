"""لا علامةَ تعارضِ دمجٍ في ملفٍّ متتبَّع.

بقي سطرُ `=======` وحده في `static/css/custom.css` بعد حلّ تعارض. والمتصفّحُ لا
يُخطئ بصوتٍ عالٍ: قرأ `======= .ui-kpis {…}` محدِّداً غيرَ صالحٍ فأسقط القاعدةَ
كلَّها بصمت — فتراصّت بطاقاتُ الأرقام في لوحة المدير على الإنتاج واحدةً تحت
أخرى بعرض الصفحة، ولا خطأَ في سجلٍّ ولا اختبار.
"""

import re
import subprocess

MARKER = re.compile(r"^(?:<{7}|={7}|>{7}|\|{7})(?: |$)", re.M)
CHECKED = (".css", ".js", ".html", ".py", ".json", ".txt", ".toml", ".yml", ".yaml", ".cfg", ".ini")


def _tracked_files():
    out = subprocess.run(["git", "ls-files", "-z"], capture_output=True, check=True).stdout.decode(
        "utf-8"
    )
    return [name for name in out.split("\0") if name.endswith(CHECKED)]


def test_no_tracked_file_carries_a_merge_conflict_marker():
    offenders = []
    for name in _tracked_files():
        if name.endswith(".min.css") or name.endswith(".min.js"):
            continue
        try:
            text = open(name, encoding="utf-8").read()
        except (FileNotFoundError, UnicodeDecodeError):
            continue
        for match in MARKER.finditer(text):
            offenders.append(f"{name}:{text.count(chr(10), 0, match.start()) + 1}")
    assert not offenders, "علامةُ تعارضِ دمجٍ بقيت في:\n  " + "\n  ".join(offenders)


def test_the_marker_pattern_catches_each_kind_and_spares_prose():
    for line in ("<<<<<<< HEAD", "=======", ">>>>>>> origin/main", "||||||| base"):
        assert MARKER.search(line)
    for line in ("/* ======= قسم ======= */", "  =======", "========", "a ======= b"):
        assert not MARKER.search(line)

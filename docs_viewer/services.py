"""عارضُ md المركزيّ — قراءةُ ملفّات التوثيق من القرص حيّاً وتصييرُها (W-20260930-002).

القاعدةُ الوحيدة هنا: **لا خروجَ عن `DOCS_ROOT`**. المسارُ مُدخَلٌ من المستخدم (جزءٌ
من الرابط)، فـ`safe_resolve` تحلّ الرمزيّاتِ (`resolve()`) ثمّ تتحقّق أنّ الناتج
داخل الجذر بـ`is_relative_to` — لا مقارنةَ نصّيّةً تخدعها `..` أو رابطٌ رمزيّ.
"""

from __future__ import annotations

import os
import re
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path

from django.conf import settings
from django.core.cache import cache
from django.http import Http404

#: جذرُ المشروع — نفسُ BASE_DIR، فيشمل `.claude/` (طلبُ المالك صراحةً).
DOCS_ROOT = Path(settings.BASE_DIR).resolve()

#: مجلّداتٌ تُستبعد من الشجرة: توليدٌ أو تبعيّاتٌ أو تاريخُ غيت — لا توثيقَ فيها.
EXCLUDED_DIR_NAMES = {
    ".git",
    "node_modules",
    "staticfiles",
    "media",
    "__pycache__",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    "venv",
    ".venv",
    "dist",
    "build",
    "logs",
    ".idea",
    ".vscode",
}

#: استثناءٌ صريحٌ من قاعدة «تجاهُل كلّ مجلّدٍ بنقطة»: `.claude/` فيها مهاراتٌ وذاكرةٌ
#: طلب المالكُ عرضَها صراحةً (بطاقةُ W-20260930-002).
ALLOWED_DOT_DIRS = {".claude"}


@dataclass
class DocNode:
    """مجلّدٌ أو ملفٌّ في شجرة العرض.

    `name` عنوانُ عرضٍ (عنوانُ الملفّ الأوّل #H1 إن وُجد، لا اسمُ الملفّ الخام —
    طلبُ المالك 2026-09-30: يُعبّر عن محتوى الملفّ)، و`filename` الاسمُ الحقيقيّ
    على القرص (يظهر في `title=` للتلميح عند التشابه)."""

    name: str
    rel_path: str
    is_dir: bool
    filename: str = ""
    children: list[DocNode] = field(default_factory=list)


def _resolve_within_root(rel_path: str) -> Path:
    """يحلّ مساراً نسبيّاً داخل `DOCS_ROOT` وحدَه، أو يرفع Http404 — الحارسُ
    المشترك بين `safe_resolve` (ملفّات md) و`resolve_asset` (صورُ الملفّات).

    `resolve()` يبتلع `..` والروابطَ الرمزيّة، و`is_relative_to` يتحقّق من الناتج
    لا من النصّ الخام — فـ`../../etc/passwd` أو رابطٌ رمزيٌّ يخرج بها يُرفض هنا.
    """
    candidate = (DOCS_ROOT / rel_path).resolve()
    if not candidate.is_relative_to(DOCS_ROOT):
        raise Http404("مسارٌ خارج جذر المشروع")
    if not candidate.is_file():
        raise Http404("الملفُّ غير موجود")
    return candidate


def safe_resolve(rel_path: str) -> Path:
    """يحلّ ملفَّ md داخل `DOCS_ROOT` وحدَه، أو يرفع Http404."""
    candidate = _resolve_within_root(rel_path)
    if candidate.suffix.lower() != ".md":
        raise Http404("ليس ملفَّ md")
    return candidate


#: الصورُ التي قد تُشار إليها من md نسبيّاً (شعاراتٌ في الوثائق غالباً) — قائمةٌ
#: مُصرَّحةٌ صراحةً لا أيَّ امتداد، فلا يتحوّل مسارُ الصور نافذةً تُسرَّب منها
#: ملفّاتٌ أخرى (`.env`, `.py`, …) عبر الرابط النسبيّ نفسِه.
ALLOWED_ASSET_SUFFIXES = {".svg", ".png", ".jpg", ".jpeg", ".gif", ".webp", ".ico"}


def resolve_asset(rel_path: str) -> Path:
    """يحلّ صورةً (شعارٌ ونحوه) داخل `DOCS_ROOT` وحدَه — امتدادٌ مُصرَّحٌ صراحةً،
    أو Http404 (`docs_viewer/rendering.py::_rewrite_relative_images` هو ما يبني
    هذا الرابط، فلا يصل هذا العرضَ مسارٌ لم يُكتب داخل md أصلاً)."""
    candidate = _resolve_within_root(rel_path)
    if candidate.suffix.lower() not in ALLOWED_ASSET_SUFFIXES:
        raise Http404("امتدادُ ملفٍّ غيرُ مسموحٍ لعرض الصور")
    return candidate


#: بناءُ الشجرة يفتح كلَّ ملفّ md (٢٣٩+) لاستخراج عنوانه — بطيءٌ محسوسٌ لو تكرّر
#: مع كلّ عرض ملفّ (كان سببَ بطء الصفحة، 2026-09-30؛ ٤+ ثوانٍ فوق Docker/ويندوز
#: رغم التخزين المؤقّت الأوّل، لأنّ كلَّ عشرين ثانيةً طلبٌ يدفع الثمنَ كاملاً من
#: جديد). عولج الأمرُ من جذره في `_build_tree_uncached`: فتحٌ متوازٍ بخيوطٍ
#: (الكلفةُ إدخالٌ/إخراجٌ لا حساب، فالخيوطُ تتداخل رغم GIL) لا تتابعيّاً، وقراءةُ
#: كلّ مجلّدٍ لمحتوياته مرّةً واحدة (`os.walk` نفسِه) لا مرّتين (عنوانُ الملفّات
#: ثمّ `iterdir()` ثانيةً لعنوان المجلّد). والتخزينُ المؤقّت طبقةٌ ثانيةٌ فوق هذا،
#: لا بديلاً عنه.
TREE_CACHE_KEY = "docs_viewer:tree"
#: حتى بعد التوازي (٢.٥ث~ بدل ٤+) يبقى الفتحُ الباردُ محسوساً — عبورُ bind-mount
#: دوكر على ويندوز كلفةٌ بنيويّةٌ لا يُزيلها تطبيقٌ. فخمسُ دقائق لا عشرون ثانية:
#: التصفّحُ العاديّ يبقى شبه فوريّ، والتعديلُ يظهر خلال دقائقَ لا ثوانٍ — توازنٌ
#: معقول لأداة مطوّرٍ داخليّة، لا وثيقةً يُنتظر ظهورُها لحظيّاً.
TREE_CACHE_SECONDS = 300
#: خيوطُ فتح الملفّات المتوازي — الإدخال/الإخراج يتداخل بينها رغم GIL، فعددٌ
#: أكبر من أنوية المعالج مفيدٌ هنا لا ضارّاً (انتظارُ قرصٍ لا حسابٌ).
_TITLE_WORKERS = 16


def build_tree() -> DocNode:
    """شجرةُ ملفّات `.md` تحت `DOCS_ROOT` — من ذاكرةٍ مؤقّتةٍ قصيرة (`TREE_CACHE_SECONDS`)،
    وإلّا تُبنى من القرص وتُخزَّن. عدِّل ملفّاً فيتأخّر ظهورُه في الشجرة عشرين
    ثانيةً أقصى — لا فوراً، ولا يوماً بعد."""
    cached = cache.get(TREE_CACHE_KEY)
    if cached is not None:
        return cached
    tree = _build_tree_uncached()
    cache.set(TREE_CACHE_KEY, tree, TREE_CACHE_SECONDS)
    return tree


def _build_tree_uncached() -> DocNode:
    # مسحٌ أوّليٌّ رخيصٌ (os.walk نفسُه لا يفتح ملفّاتٍ) يجمع كلَّ دليلٍ وأسماءَ
    # ملفّاته كاملةً — لا md وحدَها، فتُستعمَل لاحقاً لعنوان المجلّد (`_folder_title`)
    # بلا `iterdir()` ثانية لكلّ مجلّد.
    dir_all_names: dict[str, list[str]] = {}
    file_entries: list[tuple[str, str, str]] = []  # (rel_dir, filename, file_rel)

    for dirpath, dirnames, filenames in os.walk(DOCS_ROOT):
        dirnames[:] = sorted(
            d
            for d in dirnames
            if d not in EXCLUDED_DIR_NAMES and (d in ALLOWED_DOT_DIRS or not d.startswith("."))
        )
        rel_dir = os.path.relpath(dirpath, DOCS_ROOT)
        rel_dir = "" if rel_dir == "." else rel_dir.replace(os.sep, "/")
        dir_all_names[rel_dir] = filenames

        md_files = sorted(f for f in filenames if f.lower().endswith(".md"))
        for filename in md_files:
            file_rel = f"{rel_dir}/{filename}" if rel_dir else filename
            file_entries.append((rel_dir, filename, file_rel))

    # الخطوةُ البطيئة فعلاً (فتحُ كلّ ملفٍّ لاستخراج عنوانه) — بالتوازي بخيوطٍ لا
    # تتابعيّاً؛ هذا وحدَه خفّض زمن ٢٣٩+ ملفّاً من ثوانٍ إلى كسورٍ منها.
    def _title_for(entry: tuple[str, str, str]) -> str:
        rel_dir, filename, _ = entry
        return _display_title(DOCS_ROOT / rel_dir / filename, fallback=filename)

    if file_entries:
        with ThreadPoolExecutor(max_workers=_TITLE_WORKERS) as pool:
            titles = list(pool.map(_title_for, file_entries))
    else:
        titles = []

    root = DocNode(name="/", rel_path="", is_dir=True)
    nodes_by_rel: dict[str, DocNode] = {"": root}
    for (rel_dir, filename, file_rel), title in zip(file_entries, titles, strict=True):
        parent = _ensure_dir_node(nodes_by_rel, rel_dir)
        parent.children.append(
            DocNode(name=title, rel_path=file_rel, is_dir=False, filename=filename)
        )

    _prune_empty(root)
    _apply_folder_titles(root, dir_all_names)
    return root


def _ensure_dir_node(nodes_by_rel: dict[str, DocNode], rel_dir: str) -> DocNode:
    if rel_dir in nodes_by_rel:
        return nodes_by_rel[rel_dir]
    parent_rel, _, name = rel_dir.rpartition("/")
    parent = _ensure_dir_node(nodes_by_rel, parent_rel)
    raw_name = name or rel_dir
    node = DocNode(name=raw_name, rel_path=rel_dir, is_dir=True, filename=raw_name)
    parent.children.append(node)
    nodes_by_rel[rel_dir] = node
    return node


#: ملفّاتُ الفهرسة الشائعة — عنوانُ أوّلها الموجود يصير اسمَ المجلّد المعروض
#: (طلبُ المالك 2026-09-30: التعريبُ يشمل أسماء المجلّدات أيضاً، لا الملفّات وحدَها).
_FOLDER_TITLE_FILES = ("README.md", "index.md")


def _folder_title(rel_dir: str, dir_all_names: dict[str, list[str]]) -> str | None:
    """عنوانُ README/index داخل المجلّد، إن وُجد وله عنوانٌ فعليّ — وإلّا None
    (فيبقى اسمُ المجلّد الخام). `dir_all_names` من مسح `_build_tree_uncached`
    الأوّليّ — لا `iterdir()` ثانيةً لكلّ مجلّد."""
    names_lower = {n.lower(): n for n in dir_all_names.get(rel_dir, [])}
    for candidate_name in _FOLDER_TITLE_FILES:
        real_name = names_lower.get(candidate_name.lower())
        if real_name:
            title = _display_title(DOCS_ROOT / rel_dir / real_name, fallback="")
            if title:
                return title
    return None


def _apply_folder_titles(node: DocNode, dir_all_names: dict[str, list[str]]) -> None:
    for child in node.children:
        if child.is_dir:
            title = _folder_title(child.rel_path, dir_all_names)
            if title:
                child.name = title
            _apply_folder_titles(child, dir_all_names)


#: أوّلُ سطرِ عنوانٍ (`# `..`###### `) — لا كتلُ شيفرةٍ (` ``` `) فأسطرُ التعليقات
#: الموجَّهة بـ`#` داخلها ليست عناوين.
_HEADING_RE = re.compile(r"^#{1,6}\s+(.+?)\s*#*\s*$")
#: عنوانُ `<h1>` خام على سطرٍ واحد — بعضُ ملفّات المشروع (`README.md`) تكتب
#: عنوانَها HTML لا md (لتوسيط الشعار)، وإلّا بقي عارضُها اسمَ الملفّ لا محتواه.
_HTML_H1_RE = re.compile(r"<h1[^>]*>(.*?)</h1>", re.IGNORECASE)
_HTML_TAG_RE = re.compile(r"<[^>]+>")
#: سطورٌ تُفحَص قبل اليأس من وجود عنوانٍ — يكفي مقدّمةَ الملفّ، لا قراءتَه كاملاً.
_TITLE_SCAN_LINES = 80


def _first_heading(lines: list[str]) -> str | None:
    """أوّلُ عنوانٍ في الأسطر المُعطاة — md (`#`) أو `<h1>` HTML خام، أيُّهما
    يسبق الآخر في الملفّ (لا الأوّلُ نوعاً)؛ يتخطّى كتلَ الشيفرة (` ``` `) فـ`#`
    داخلها تعليقٌ لا عنوان."""
    in_code_block = False
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("```") or stripped.startswith("~~~"):
            in_code_block = not in_code_block
            continue
        if in_code_block:
            continue
        match = _HEADING_RE.match(stripped)
        if match:
            return match.group(1).strip()
        html_match = _HTML_H1_RE.search(stripped)
        if html_match:
            return _HTML_TAG_RE.sub("", html_match.group(1)).strip()
    return None


def _display_title(path: Path, fallback: str) -> str:
    """عنوانُ العرض في الشجرة: أوّلُ عنوانِ md في الملفّ (مقدّمتُه فقط)، أو اسمُ
    الملفّ إن غاب — قراءةٌ جزئيّةٌ (`_TITLE_SCAN_LINES`) لخفّة بناء شجرةٍ من مئات
    الملفّات، لا الملفَّ كاملاً."""
    try:
        with path.open(encoding="utf-8", errors="replace") as fh:
            lines = [line for _, line in zip(range(_TITLE_SCAN_LINES), fh, strict=False)]
    except OSError:
        return fallback
    return _first_heading(lines) or fallback


def extract_title(text: str, fallback: str) -> str:
    """عنوانُ العرض من نصٍّ مقروءٍ أصلاً بالكامل (صفحةُ التفصيل) — لا فتحَ ملفٍّ
    ثانيةً؛ نفسُ منطق `_display_title` على أسطر النصّ المُعطى."""
    return _first_heading(text.splitlines()[:_TITLE_SCAN_LINES]) or fallback


def _prune_empty(node: DocNode) -> None:
    for child in list(node.children):
        if child.is_dir:
            _prune_empty(child)
    node.children.sort(key=lambda n: (not n.is_dir, n.name.lower()))


def ancestor_dirs(rel_path: str) -> set[str]:
    """مجلّداتُ المسار الأصليّة — لفتح سلسلة المجلّدات المؤدّية إلى الملفّ المفتوح
    وحدَها في شجرة التصفّح، لا الشجرةَ كلَّها (الحالةُ الافتراضيّةُ مطويّة)."""
    parts = rel_path.rsplit("/", 1)[0].split("/") if "/" in rel_path else []
    dirs: set[str] = set()
    built = ""
    for part in parts:
        built = f"{built}/{part}" if built else part
        dirs.add(built)
    return dirs


# ── بحثُ المحتوى (طلبُ المالك 2026-09-30: فوريٌّ بالأسماء + بحثٌ في المحتوى) ──


@dataclass
class SearchResult:
    """نتيجةُ بحثٍ في محتوى ملفّ: مقتطفٌ حول أوّل تطابق."""

    rel_path: str
    title: str
    snippet: str


#: محتوى كلّ الملفّات كاملاً — أثقلُ من الشجرة (٨٠ سطراً للعنوان فقط) فمفتاحٌ
#: مستقلّ؛ نفسُ مدّة التخزين والتوازي (`_build_tree_uncached`). لا يُبنى إلا
#: عند أوّل بحثٍ فعليّ — لا كلفةَ على فتح صفحةٍ عاديّة لا تستعمل البحث.
CORPUS_CACHE_KEY = "docs_viewer:corpus"


def build_corpus() -> list[tuple[str, str, str]]:
    """`[(rel_path, title, النصّ الكامل)]` لكلّ ملفّ md — من ذاكرةٍ مؤقّتةٍ
    (`TREE_CACHE_SECONDS`) وإلّا تُبنى بالتوازي وتُخزَّن."""
    cached = cache.get(CORPUS_CACHE_KEY)
    if cached is not None:
        return cached
    corpus = _build_corpus_uncached()
    cache.set(CORPUS_CACHE_KEY, corpus, TREE_CACHE_SECONDS)
    return corpus


def _build_corpus_uncached() -> list[tuple[str, str, str]]:
    file_entries: list[tuple[str, str]] = []  # (rel_dir, filename)
    for dirpath, dirnames, filenames in os.walk(DOCS_ROOT):
        dirnames[:] = sorted(
            d
            for d in dirnames
            if d not in EXCLUDED_DIR_NAMES and (d in ALLOWED_DOT_DIRS or not d.startswith("."))
        )
        rel_dir = os.path.relpath(dirpath, DOCS_ROOT)
        rel_dir = "" if rel_dir == "." else rel_dir.replace(os.sep, "/")
        for filename in sorted(f for f in filenames if f.lower().endswith(".md")):
            file_entries.append((rel_dir, filename))

    def _read(entry: tuple[str, str]) -> tuple[str, str, str]:
        rel_dir, filename = entry
        file_rel = f"{rel_dir}/{filename}" if rel_dir else filename
        try:
            text = (DOCS_ROOT / rel_dir / filename).read_text(encoding="utf-8", errors="replace")
        except OSError:
            text = ""
        title = _first_heading(text.splitlines()[:_TITLE_SCAN_LINES]) or filename
        return (file_rel, title, text)

    if not file_entries:
        return []
    with ThreadPoolExecutor(max_workers=_TITLE_WORKERS) as pool:
        return list(pool.map(_read, file_entries))


#: نصفُ طول المقتطف حول أوّل تطابق (حرفاً) على كلّ جهة.
_SNIPPET_RADIUS = 60
_SEARCH_RESULT_LIMIT = 30


def search_content(query: str, limit: int = _SEARCH_RESULT_LIMIT) -> list[SearchResult]:
    """بحثٌ حرفيٌّ (غيرُ حسّاسٍ لحالة الأحرف) في محتوى كلّ ملفّات md — أوّلُ
    تطابقٍ في كلّ ملفٍّ وحدَه، بمقتطفٍ حوله."""
    query = query.strip()
    if len(query) < 2:
        return []
    needle = query.lower()
    results: list[SearchResult] = []
    for rel_path, title, text in build_corpus():
        idx = text.lower().find(needle)
        if idx == -1:
            continue
        start = max(0, idx - _SNIPPET_RADIUS)
        end = min(len(text), idx + len(query) + _SNIPPET_RADIUS)
        snippet = " ".join(text[start:end].split())
        if start > 0:
            snippet = "…" + snippet
        if end < len(text):
            snippet += "…"
        results.append(SearchResult(rel_path=rel_path, title=title, snippet=snippet))
        if len(results) >= limit:
            break
    return results
